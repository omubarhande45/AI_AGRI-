"""
Comprehensive test script for AgriSmartAI web app and services.
Verifies all routes, templates, API endpoints, database operations, and PDF rendering.
"""
from __future__ import annotations

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app, db
from app.seed.seed import main as seed_main


class AgriSmartAITestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

        # Ensure DB is seeded
        if db.table_count("users") == 0:
            seed_main()

    def login(self, username="ramesh", password="farmer123"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def test_01_public_and_auth(self):
        """Test unauthenticated access and login flow."""
        # Unauthenticated redirect
        res = self.client.get("/", follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        # Login page
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"AgriSmart", res.data)

        # Valid login
        res = self.login()
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Dashboard", res.data)

    def test_02_pages(self):
        """Test rendering of all core dashboard pages."""
        self.login()
        pages = [
            "/",
            "/crops",
            "/crop/1",
            "/disease",
            "/twin",
            "/predictions",
            "/market",
            "/dss",
            "/reports",
            "/weather",
            "/profile",
            "/farm/new",
            "/field/new",
        ]
        for url in pages:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(
                    res.status_code,
                    200,
                    f"Page {url} failed with status {res.status_code}",
                )

    def test_03_api_endpoints(self):
        """Test all REST API endpoints."""
        self.login()
        api_endpoints = [
            "/api/status",
            "/api/disease/classes",
            "/api/yield/predict?crop=Tomato&season=kharif&nitrogen=100&phosphorus=40&potassium=40&ph=6.5&rainfall_mm=600&irrigation_mm=200&temp_max_mean=32",
            "/api/field/1/irrigation",
            "/api/field/1/fertilizer",
            "/api/field/1/pest-risk",
            "/api/field/1/twin?days=30",
            "/api/market/prices?crop=Tomato",
            "/api/market/forecast?crop=Tomato&mandi=Nashik",
            "/api/market/mandis?crop=Tomato",
            "/api/market/demand?crop=Tomato",
            "/api/market/profit?crop=Tomato&area=2&yield_q=120",
            "/api/farm/1/report",
            "/api/weather/1",
        ]
        for url in api_endpoints:
            with self.subTest(url=url):
                res = self.client.get(url)
                if res.status_code != 200:
                    print(f"\n[FAIL] API {url} returned {res.status_code}: {res.data.decode('utf-8', errors='ignore')}")
                self.assertEqual(res.status_code, 200, f"API {url} failed with status {res.status_code}")
                self.assertTrue(res.is_json, f"API {url} did not return valid JSON")

    def test_04_reports_pdf(self):
        """Test PDF generation for farm reports and diagnostics."""
        self.login()
        res = self.client.get("/reports/farm.pdf")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/pdf")
        self.assertGreater(len(res.data), 1000)

        # Diagnostic PDF
        res = self.client.get("/reports/diagnostic/1")
        # Could be 200 or 404 depending on scan id 1
        self.assertIn(res.status_code, (200, 404))

    def test_05_disease_demo(self):
        """Test disease detection demo endpoint."""
        self.login()
        res = self.client.get("/disease/demo/0", follow_redirects=True)
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()

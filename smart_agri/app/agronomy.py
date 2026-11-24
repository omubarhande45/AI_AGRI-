"""Agronomic domain data for Maharashtra crops.

Every number here is a realistic published-range value used by the
recommendation engine, the digital twin and the profit model. They are
*defaults*: the ML models learn deviations from them using the seeded
historical data, and the farmer can override anything from the UI.

Units: yield kg/acre, water mm/season, nutrients kg/acre N-P2O5-K2O, costs INR/acre.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CropProfile:
    name: str
    seasons: tuple[str, ...]
    duration_days: int
    yield_kg_per_acre: float          # typical
    yield_range: tuple[float, float]  # (pessimistic, optimistic)
    water_mm_season: float            # total irrigation requirement
    critical_stage: str               # growth stage most sensitive to water stress
    npk_kg_per_acre: tuple[float, float, float]   # N, P2O5, K2O
    cost_per_acre: float              # total cost of cultivation, INR
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    pests: tuple[str, ...] = ()
    diseases: tuple[str, ...] = ()
    base_price_per_q: float = 0.0     # INR/quintal, seeded around this
    price_volatility: float = 0.06    # monthly sigma
    shelf_life_days: int = 5
    harvest_window_days: int = 14     # flexibility around optimal harvest

    @property
    def breakeven_price(self) -> float:
        """INR/quintal needed to cover the cost of cultivation."""
        return self.cost_per_acre / max(self.yield_kg_per_acre / 100.0, 1e-6)


CROPS: dict[str, CropProfile] = {
    "Grape": CropProfile(
        name="Grape", seasons=("rabi",), duration_days=150,
        yield_kg_per_acre=9000, yield_range=(5500, 13000),
        water_mm_season=700, critical_stage="berry swell",
        npk_kg_per_acre=(200, 100, 160), cost_per_acre=145000,
        cost_breakdown={"Pruning & labour": 42000, "Fertilizer & spray": 46000,
                        "Irrigation & power": 22000, "Canopy & trellis": 18000,
                        "Harvest & packing": 17000},
        pests=("Thrips", "Mealybug", "Fruit borer", "Spider mite"),
        diseases=("Powdery mildew", "Downy mildew", "Anthracnose", "Black rot"),
        base_price_per_q=4200, price_volatility=0.11, shelf_life_days=12,
        harvest_window_days=21,
    ),
    "Onion": CropProfile(
        name="Onion", seasons=("kharif", "rabi"), duration_days=130,
        yield_kg_per_acre=110, yield_range=(70, 165),
        water_mm_season=420, critical_stage="bulb development",
        npk_kg_per_acre=(40, 20, 20), cost_per_acre=26000,
        cost_breakdown={"Seed & nursery": 4500, "Land prep & labour": 8000,
                        "Fertilizer & spray": 7000, "Irrigation & power": 3500,
                        "Harvest & grading": 3000},
        pests=("Thrips", "Onion maggot", "Leaf miner"),
        diseases=("Purple blotch", "Downy mildew", "Basal rot"),
        base_price_per_q=1850, price_volatility=0.22, shelf_life_days=45,
        harvest_window_days=14,
    ),
    "Tomato": CropProfile(
        name="Tomato", seasons=("kharif", "rabi", "summer"), duration_days=120,
        yield_kg_per_acre=150, yield_range=(95, 220),
        water_mm_season=480, critical_stage="flowering & fruit set",
        npk_kg_per_acre=(48, 24, 24), cost_per_acre=34000,
        cost_breakdown={"Seedling & nursery": 5000, "Land prep & labour": 9000,
                        "Staking & mulch": 6000, "Fertilizer & spray": 8500,
                        "Irrigation & power": 2500, "Harvest": 3000},
        pests=("Fruit borer", "Whitefly", "Leaf miner", "Two-spotted spider mite"),
        diseases=("Early blight", "Late blight", "Leaf mold", "Septoria leaf spot",
                  "Bacterial spot", "Tomato yellow leaf curl virus", "Target spot",
                  "Tomato mosaic virus"),
        base_price_per_q=1450, price_volatility=0.26, shelf_life_days=6,
        harvest_window_days=10,
    ),
    "Maize": CropProfile(
        name="Maize", seasons=("kharif", "rabi"), duration_days=110,
        yield_kg_per_acre=22, yield_range=(15, 32),
        water_mm_season=450, critical_stage="tasselling & silking",
        npk_kg_per_acre=(60, 30, 30), cost_per_acre=16500,
        cost_breakdown={"Seed": 3200, "Land prep": 3500, "Fertilizer": 4200,
                        "Plant protection": 1600, "Irrigation & power": 1800,
                        "Harvest & threshing": 2200},
        pests=("Fall armyworm", "Stem borer", "Shoot fly"),
        diseases=("Common rust", "Northern leaf blight", "Cercospora grey leaf spot",
                  "Maize lethal necrosis"),
        base_price_per_q=2150, price_volatility=0.08, shelf_life_days=180,
        harvest_window_days=14,
    ),
    "Potato": CropProfile(
        name="Potato", seasons=("rabi",), duration_days=100,
        yield_kg_per_acre=100, yield_range=(65, 145),
        water_mm_season=380, critical_stage="tuber initiation",
        npk_kg_per_acre=(72, 32, 32), cost_per_acre=38000,
        cost_breakdown={"Seed tubers": 15000, "Land prep & labour": 7000,
                        "Fertilizer": 6000, "Plant protection": 5000,
                        "Irrigation & power": 2500, "Harvest & storage": 2500},
        pests=("Aphid", "Potato tuber moth", "White grub"),
        diseases=("Early blight", "Late blight", "Black scurf", "Common scab"),
        base_price_per_q=1300, price_volatility=0.16, shelf_life_days=90,
        harvest_window_days=12,
    ),
    "Sugarcane": CropProfile(
        name="Sugarcane", seasons=("kharif",), duration_days=330,
        yield_kg_per_acre=480, yield_range=(340, 620),
        water_mm_season=1800, critical_stage="grand growth",
        npk_kg_per_acre=(112, 56, 56), cost_per_acre=92000,
        cost_breakdown={"Seed & planting": 22000, "Land prep & labour": 20000,
                        "Fertilizer": 16000, "Irrigation & power": 24000,
                        "Plant protection": 4000, "Harvest": 6000},
        pests=("Early shoot borer", "Pyrilla", "White grub"),
        diseases=("Red rot", "Smut", "Wilt", "Grassy shoot"),
        base_price_per_q=315, price_volatility=0.03, shelf_life_days=3,
        harvest_window_days=45,
    ),
    "Cotton": CropProfile(
        name="Cotton", seasons=("kharif",), duration_days=165,
        yield_kg_per_acre=7, yield_range=(4, 11),
        water_mm_season=600, critical_stage="boll development",
        npk_kg_per_acre=(48, 24, 24), cost_per_acre=24000,
        cost_breakdown={"Seed (Bt)": 3600, "Land prep": 4000, "Fertilizer": 4500,
                        "Plant protection": 6500, "Irrigation & power": 2200,
                        "Picking": 3200},
        pests=("Pink bollworm", "Whitefly", "Jassid", "Thrips", "Mealybug"),
        diseases=("Bacterial blight", "Fusarium wilt", "Leaf curl virus"),
        base_price_per_q=7000, price_volatility=0.07, shelf_life_days=365,
        harvest_window_days=30,
    ),
    "Soybean": CropProfile(
        name="Soybean", seasons=("kharif",), duration_days=100,
        yield_kg_per_acre=6, yield_range=(4, 9),
        water_mm_season=450, critical_stage="pod filling",
        npk_kg_per_acre=(12, 32, 8), cost_per_acre=11000,
        cost_breakdown={"Seed": 1600, "Land prep": 2600, "Fertilizer": 1800,
                        "Plant protection": 1200, "Harvest & threshing": 3800},
        pests=("Girdle beetle", "Semilooper", "Stem fly"),
        diseases=("Yellow mosaic virus", "Rust", "Charcoal rot"),
        base_price_per_q=4600, price_volatility=0.06, shelf_life_days=240,
        harvest_window_days=10,
    ),
    "Pomegranate": CropProfile(
        name="Pomegranate", seasons=("rabi", "summer"), duration_days=180,
        yield_kg_per_acre=60, yield_range=(35, 85),
        water_mm_season=800, critical_stage="fruit development",
        npk_kg_per_acre=(160, 80, 160), cost_per_acre=78000,
        cost_breakdown={"Pruning & labour": 24000, "Fertilizer & spray": 22000,
                        "Irrigation & power": 16000, "Bagging & fruit fly mgmt": 9000,
                        "Harvest & packing": 7000},
        pests=("Fruit borer", "Thrips", "Sucking pests"),
        diseases=("Anthracnose", "Fruit rot", "Wilt", "Sooty blotch"),
        base_price_per_q=6500, price_volatility=0.13, shelf_life_days=25,
        harvest_window_days=20,
    ),
    "Pigeon pea (Tur)": CropProfile(
        name="Pigeon pea (Tur)", seasons=("kharif",), duration_days=160,
        yield_kg_per_acre=4, yield_range=(2, 7),
        water_mm_season=380, critical_stage="flowering & pod set",
        npk_kg_per_acre=(10, 20, 8), cost_per_acre=9500,
        cost_breakdown={"Seed": 1200, "Land prep": 2400, "Fertilizer": 1400,
                        "Plant protection": 1500, "Harvest & threshing": 3000},
        pests=("Pod borer", "Pod fly", "Pod bug"),
        diseases=("Fusarium wilt", "Sterility mosaic", "Leaf spot"),
        base_price_per_q=10500, price_volatility=0.09, shelf_life_days=300,
        harvest_window_days=14,
    ),
    "Wheat": CropProfile(
        name="Wheat", seasons=("rabi",), duration_days=120,
        yield_kg_per_acre=12, yield_range=(8, 17),
        water_mm_season=420, critical_stage="crown root & grain filling",
        npk_kg_per_acre=(48, 24, 16), cost_per_acre=13500,
        cost_breakdown={"Seed": 1800, "Land prep": 2800, "Fertilizer": 3200,
                        "Plant protection": 900, "Irrigation & power": 1600,
                        "Harvest & threshing": 3200},
        pests=("Aphid", "Termites"),
        diseases=("Yellow rust", "Karnal bunt", "Loose smut"),
        base_price_per_q=2450, price_volatility=0.04, shelf_life_days=365,
        harvest_window_days=14,
    ),
    "Banana": CropProfile(
        name="Banana", seasons=("kharif", "rabi"), duration_days=330,
        yield_kg_per_acre=1300, yield_range=(900, 1800),
        water_mm_season=1500, critical_stage="bunch development",
        npk_kg_per_acre=(240, 96, 320), cost_per_acre=120000,
        cost_breakdown={"Suckers & planting": 30000, "Fertilizer": 32000,
                        "Irrigation & power": 24000, "Plant protection": 14000,
                        "Labour": 12000, "Harvest & packing": 8000},
        pests=("Banana pseudostem weevil", "Banana aphid", "Thrips"),
        diseases=("Panama wilt", "Sigatoka leaf spot", "Bunchy top virus"),
        base_price_per_q=1650, price_volatility=0.14, shelf_life_days=8,
        harvest_window_days=21,
    ),
    "Bell pepper": CropProfile(
        name="Bell pepper", seasons=("rabi", "summer"), duration_days=150,
        yield_kg_per_acre=120, yield_range=(75, 175),
        water_mm_season=550, critical_stage="flowering & fruit set",
        npk_kg_per_acre=(64, 32, 40), cost_per_acre=95000,
        cost_breakdown={"Seedling (polyhouse)": 34000, "Fertilizer & fertigation": 26000,
                        "Plant protection": 12000, "Irrigation & power": 10000,
                        "Labour": 8000, "Packing": 5000},
        pests=("Thrips", "Mites", "Whitefly"),
        diseases=("Bacterial spot", "Powdery mildew", "Anthracnose"),
        base_price_per_q=3800, price_volatility=0.18, shelf_life_days=10,
        harvest_window_days=25,
    ),
    "Squash": CropProfile(
        name="Squash", seasons=("kharif", "summer"), duration_days=90,
        yield_kg_per_acre=90, yield_range=(60, 130),
        water_mm_season=400, critical_stage="fruit set",
        npk_kg_per_acre=(40, 20, 20), cost_per_acre=28000,
        cost_breakdown={"Seed": 3000, "Land prep": 6000, "Fertilizer & spray": 9000,
                        "Irrigation & power": 4000, "Harvest": 6000},
        pests=("Fruit fly", "Aphid", "Beetle"),
        diseases=("Powdery mildew", "Downy mildew", "Mosaic virus"),
        base_price_per_q=1200, price_volatility=0.15, shelf_life_days=14,
        harvest_window_days=12,
    ),
}


def get_crop(name: str) -> CropProfile | None:
    if not name:
        return None
    key = name.strip()
    if key in CROPS:
        return CROPS[key]
    low = key.lower()
    for k, v in CROPS.items():
        if k.lower() == low:
            return v
    for k, v in CROPS.items():
        if low in k.lower() or k.lower() in low:
            return v
    return None


CROP_NAMES = list(CROPS.keys())


# ---------------------------------------------------------------------------
# Disease knowledge base.
# Keys are the PlantVillage class names the CNN emits; values are what the
# Decision Support System shows the farmer.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DiseaseInfo:
    crop: str
    display_name: str
    pathogen_type: str        # fungal / bacterial / viral / mite / none
    severity_weight: float    # 0 (healthy) .. 1 (severe)
    symptoms: str
    management: tuple[str, ...]
    yield_loss_pct: float     # if untreated
    spread_risk: str          # low / moderate / high
    organic: str


_D = DiseaseInfo
DISEASE_DB: dict[str, DiseaseInfo] = {
    # ---- Healthy ---------------------------------------------------------
    "Apple___healthy": _D("Apple", "Healthy apple leaf", "none", 0.0,
        "Uniform green lamina, no lesions or discolouration.",
        ("No treatment needed. Continue scheduled nutrition and irrigation.",),
        0.0, "low", "Maintain mulch and balanced NPK."),
    "Blueberry___healthy": _D("Blueberry", "Healthy blueberry leaf", "none", 0.0,
        "Glossy green leaves with intact margins.", ("No action needed.",), 0.0, "low",
        "Maintain acidic soil pH 4.5-5.5."),
    "Cherry_(including_sour)___healthy": _D("Cherry", "Healthy cherry leaf", "none", 0.0,
        "Deep green, undamaged foliage.", ("No action needed.",), 0.0, "low", "Monitor after rain events."),
    "Corn_(maize)___healthy": _D("Maize", "Healthy maize leaf", "none", 0.0,
        "Deep green leaf with clear midrib, no lesions.",
        ("No treatment needed. Continue urea top-dressing at knee-high stage.",),
        0.0, "low", "Maintain 48 kg N/acre split into two doses."),
    "Grape___healthy": _D("Grape", "Healthy grape leaf", "none", 0.0,
        "Uniform green canopy, no mildew growth or spots.",
        ("No fungicide needed. Keep canopy open for airflow.",), 0.0, "low",
        "Avoid overhead irrigation after 4 pm."),
    "Peach___healthy": _D("Peach", "Healthy peach leaf", "none", 0.0,
        "Clean green foliage.", ("No action needed.",), 0.0, "low", "Monitor during humid spells."),
    "Pepper,_bell___healthy": _D("Bell pepper", "Healthy bell pepper leaf", "none", 0.0,
        "Dark green, turgid leaves with no spotting.",
        ("No treatment needed. Continue fertigation schedule.",), 0.0, "low",
        "Maintain EC 1.8-2.2 mS/cm in fertigation."),
    "Potato___healthy": _D("Potato", "Healthy potato leaf", "none", 0.0,
        "Clean compound leaf, no water-soaked patches.",
        ("No fungicide needed. Continue earthing up.",), 0.0, "low",
        "Avoid irrigation in the evening."),
    "Raspberry___healthy": _D("Raspberry", "Healthy raspberry leaf", "none", 0.0,
        "Green, undamaged foliage.", ("No action needed.",), 0.0, "low", "Maintain cane spacing."),
    "Soybean___healthy": _D("Soybean", "Healthy soybean leaf", "none", 0.0,
        "Trifoliate leaves uniformly green.", ("No action needed.",), 0.0, "low",
        "Rhizobium inoculation at sowing improves N fixation."),
    "Strawberry___healthy": _D("Strawberry", "Healthy strawberry leaf", "none", 0.0,
        "Green trifoliate leaves, no scorching.", ("No action needed.",), 0.0, "low",
        "Maintain drip irrigation and mulch."),
    "Tomato___healthy": _D("Tomato", "Healthy tomato leaf", "none", 0.0,
        "Deep green leaflets with no lesions, curling or spotting.",
        ("No treatment needed. Continue staking and balanced nutrition.",),
        0.0, "low", "Maintain 48-24-24 kg/acre NPK."),

    # ---- Tomato ----------------------------------------------------------
    "Tomato___Bacterial_spot": _D("Tomato", "Bacterial spot", "bacterial", 0.8,
        "Small dark water-soaked spots on leaves and fruit, greasy halo, leaf drop.",
        ("Remove and burn infected leaves immediately - do not compost.",
         "Spray copper oxychloride 3 g/L or Bordeaux mixture 1%.",
         "Avoid working in the field when foliage is wet.",
         "Use certified disease-free seed and rotate with cereals for 2 seasons."),
        25.0, "high", "Neem oil 5 ml/L + copper spray alternate weekly."),
    "Tomato___Early_blight": _D("Tomato", "Early blight", "fungal", 0.7,
        "Concentric 'target board' rings on lower leaves with yellow halos.",
        ("Remove lower infected leaves and mulch to stop soil splash.",
         "Spray mancozeb 2.5 g/L or azoxystrobin 1 ml/L, alternate modes of action.",
         "Improve airflow by pruning and wider spacing.",
         "Rotate with maize or pulses; avoid tomato-potato adjacency."),
        20.0, "high", "Trichoderma viride soil application + neem oil foliar spray."),
    "Tomato___Late_blight": _D("Tomato", "Late blight", "fungal", 1.0,
        "Water-soaked grey-green lesions with white downy growth on leaf undersides; rapid collapse.",
        ("Treat as an emergency - act within 24 hours.",
         "Spray cymoxanil + mancozeb 3 g/L immediately, repeat in 7 days.",
         "Destroy severely infected plants by burning.",
         "Stop overhead irrigation; improve drainage."),
        60.0, "high", "Copper hydroxide 2 g/L; destroy residues; no composting."),
    "Tomato___Leaf_Mold": _D("Tomato", "Leaf mold", "fungal", 0.55,
        "Pale yellow spots on upper leaf with olive-brown velvety mould below.",
        ("Reduce humidity: increase ventilation in polyhouse, avoid dense canopy.",
         "Spray chlorothalonil 2 g/L or difenoconazole 0.5 ml/L.",
         "Remove lower leaves and avoid wetting foliage."),
        15.0, "moderate", "Increase airflow + potassium bicarbonate 5 g/L spray."),
    "Tomato___Septoria_leaf_spot": _D("Tomato", "Septoria leaf spot", "fungal", 0.6,
        "Many small circular grey spots with dark borders on older leaves.",
        ("Remove and destroy infected lower leaves.",
         "Spray mancozeb 2.5 g/L or copper oxychloride 3 g/L every 10 days.",
         "Mulch to prevent rain splash; rotate crops."),
        18.0, "high", "Neem oil 5 ml/L + crop rotation with cereals."),
    "Tomato___Spider_mites Two-spotted_spider_mite": _D("Tomato", "Two-spotted spider mite", "mite", 0.65,
        "Fine stippling and bronzing on leaves, fine webbing, leaf drying in hot dry weather.",
        ("Spray abamectin 0.5 ml/L or spiromesifen 1 ml/L.",
         "Release predatory mites / spray neem oil in organic blocks.",
         "Increase humidity - mites thrive in hot dry conditions.",
         "Remove weeds that host mites along field borders."),
        22.0, "high", "Neem oil 5 ml/L weekly + release Phytoseiulus predators."),
    "Tomato___Target_Spot": _D("Tomato", "Target spot", "fungal", 0.7,
        "Brown lesions with concentric rings and yellow halos, often on fruit too.",
        ("Spray azoxystrobin 1 ml/L or mancozeb 2.5 g/L at first sign.",
         "Remove infected debris after harvest.",
         "Widen spacing and stake plants for airflow."),
        24.0, "high", "Trichoderma + neem oil; destroy crop debris."),
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": _D("Tomato", "Tomato yellow leaf curl virus", "viral", 0.9,
        "Upward curling and yellowing of leaves, stunted plant, flower drop.",
        ("No cure - roguing (pulling out and destroying) infected plants is essential.",
         "Control whitefly vector: yellow sticky traps 10/acre + imidacloprid 0.3 ml/L.",
         "Use virus-tolerant hybrids and 40-mesh insect-proof nursery.",
         "Remove weeds such as parthenium that host the vector."),
        45.0, "high", "Yellow sticky traps + neem oil 5 ml/L for whitefly suppression."),
    "Tomato___Tomato_mosaic_virus": _D("Tomato", "Tomato mosaic virus", "viral", 0.85,
        "Mottled light and dark green leaves, distorted growth, brown internal fruit.",
        ("Remove and destroy infected plants; do not handle healthy plants after.",
         "Disinfect tools with 3% trisodium phosphate.",
         "Use virus-free seed and avoid tobacco handling before field work."),
        35.0, "high", "Roguing + strict tool hygiene; vector control."),

    # ---- Maize -----------------------------------------------------------
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": _D("Maize", "Grey leaf spot", "fungal", 0.7,
        "Long narrow rectangular grey lesions parallel to leaf veins.",
        ("Spray azoxystrobin 1 ml/L or propiconazole 1 ml/L at tasselling.",
         "Rotate with pulses and bury residue.",
         "Avoid continuous maize in the same field."),
        20.0, "high", "Trichoderma seed treatment + residue management."),
    "Corn_(maize)___Common_rust_": _D("Maize", "Common rust", "fungal", 0.5,
        "Cinnamon-brown powdery pustules scattered on both leaf surfaces.",
        ("Spray propiconazole 1 ml/L or mancozeb 2.5 g/L if severity crosses 10%.",
         "Use resistant hybrids next season.",
         "Ensure adequate potassium nutrition."),
        12.0, "moderate", "Sulphur dust 20 kg/acre + resistant hybrid."),
    "Corn_(maize)___Northern_Leaf_Blight": _D("Maize", "Northern leaf blight", "fungal", 0.75,
        "Long cigar-shaped grey-green lesions that turn tan, spreading upward.",
        ("Spray mancozeb 2.5 g/L or azoxystrobin 1 ml/L.",
         "Rotate crops and incorporate residue.",
         "Choose tolerant hybrids."),
        22.0, "high", "Residue management + Trichoderma soil application."),

    # ---- Potato ----------------------------------------------------------
    "Potato___Early_blight": _D("Potato", "Potato early blight", "fungal", 0.6,
        "Dark concentric target spots on older leaves with yellow margins.",
        ("Spray mancozeb 2.5 g/L or chlorothalonil 2 g/L every 10 days.",
         "Maintain balanced nitrogen - avoid excess.",
         "Rotate with cereals."),
        15.0, "high", "Neem oil 5 ml/L + Trichoderma in soil."),
    "Potato___Late_blight": _D("Potato", "Potato late blight", "fungal", 1.0,
        "Water-soaked dark lesions with pale halo and white downy sporulation on leaf underside.",
        ("Emergency: spray cymoxanil + mancozeb 3 g/L within 24 hours.",
         "Destroy haulms of severely affected plants.",
         "Avoid evening irrigation and dense canopies.",
         "Harvest in dry weather to avoid tuber infection."),
        55.0, "high", "Copper oxychloride 3 g/L; destroy infected haulms."),

    # ---- Grape -----------------------------------------------------------
    "Grape___Black_rot": _D("Grape", "Grape black rot", "fungal", 0.8,
        "Brown circular leaf lesions with black pycnidia; shrivelled black mummies on berries.",
        ("Remove and destroy mummified berries - the main inoculum source.",
         "Spray mancozeb 2.5 g/L or myclobutanil 0.4 g/L before rains.",
         "Prune for an open canopy and good airflow."),
        35.0, "high", "Remove mummies + Bordeaux mixture 1% before flowering."),
    "Grape___Esca_(Black_Measles)": _D("Grape", "Esca (black measles)", "fungal", 0.85,
        "Tiger-stripe leaf pattern, dark spots on berries, eventual vine decline.",
        ("No chemical cure - prune out affected wood below the affected zone.",
         "Seal pruning wounds with copper paste within 24 hours.",
         "Remove and burn infected vines.",
         "Avoid pruning during wet weather."),
        40.0, "moderate", "Copper paste on wounds + hot water treatment of cuttings."),
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": _D("Grape", "Isariopsis leaf blight", "fungal", 0.7,
        "Irregular reddish-brown angular leaf spots with dark borders.",
        ("Spray mancozeb 2.5 g/L or copper oxychloride 3 g/L.",
         "Improve canopy aeration by leaf removal.",
         "Collect and destroy fallen leaves."),
        20.0, "high", "Bordeaux mixture 1% + canopy management."),

    # ---- Bell pepper -----------------------------------------------------
    "Pepper,_bell___Bacterial_spot": _D("Bell pepper", "Bell pepper bacterial spot", "bacterial", 0.8,
        "Small dark water-soaked spots turning brown with yellow halos on leaves and fruit.",
        ("Remove infected leaves; do not work in wet canopy.",
         "Spray copper oxychloride 3 g/L + streptomycin 0.1 g/L.",
         "Use pathogen-free seed and rotate with cereals.",),
        25.0, "high", "Copper spray + neem oil; strict seed hygiene."),

    # ---- Other crops (present in PlantVillage, out of Maharashtra focus) --
    "Apple___Apple_scab": _D("Apple", "Apple scab", "fungal", 0.75,
        "Olive-green velvety spots on leaves and corky scabs on fruit.",
        ("Spray dodine or captan from green tip stage.", "Rake and destroy fallen leaves."),
        25.0, "high", "Sulphur dust + leaf litter removal."),
    "Apple___Black_rot": _D("Apple", "Apple black rot", "fungal", 0.7,
        "Brown leaf spots with purple margins; black sunken cankers on branches.",
        ("Prune out cankers and burn them.", "Spray captan 2 g/L after petal fall."),
        20.0, "moderate", "Copper spray at dormancy + canker removal."),
    "Apple___Cedar_apple_rust": _D("Apple", "Cedar apple rust", "fungal", 0.6,
        "Bright orange-yellow spots on leaves with tube-like structures below.",
        ("Remove nearby juniper hosts.", "Spray myclobutanil 0.4 g/L before rain."),
        15.0, "moderate", "Host removal + sulphur spray."),
    "Cherry_(including_sour)___Powdery_mildew": _D("Cherry", "Cherry powdery mildew", "fungal", 0.55,
        "White powdery coating on leaves and fruit with leaf curling.",
        ("Spray wettable sulphur 2 g/L or potassium bicarbonate 5 g/L.", "Open the canopy."),
        15.0, "moderate", "Sulphur spray + improved airflow."),
    "Orange___Haunglongbing_(Citrus_greening)": _D("Orange", "Citrus greening (HLB)", "bacterial", 0.95,
        "Blotchy asymmetric leaf mottling, yellow shoots, small bitter fruit.",
        ("No cure - remove and destroy infected trees.",
         "Control the Asian citrus psyllid vector with imidacloprid.",
         "Plant certified disease-free nursery stock."),
        70.0, "high", "Vector control + certified planting material."),
    "Peach___Bacterial_spot": _D("Peach", "Peach bacterial spot", "bacterial", 0.7,
        "Dark purple-black angular leaf spots, shot-hole effect, fruit lesions.",
        ("Spray copper at dormancy and after petal fall.", "Choose resistant varieties."),
        20.0, "moderate", "Copper sprays + resistant varieties."),
    "Squash___Powdery_mildew": _D("Squash", "Squash powdery mildew", "fungal", 0.6,
        "White powdery patches on upper leaf surface, premature leaf senescence.",
        ("Spray wettable sulphur 2 g/L or potassium bicarbonate 5 g/L.",
         "Avoid excess nitrogen; keep spacing wide."),
        18.0, "high", "Neem oil 3 ml/L + milk spray 1:10 weekly."),
    "Strawberry___Leaf_scorch": _D("Strawberry", "Strawberry leaf scorch", "fungal", 0.6,
        "Dark purple irregular spots that coalesce, causing scorched leaf margins.",
        ("Remove old infected leaves.", "Spray captan 2 g/L or myclobutanil.",
         "Use drip irrigation to keep foliage dry."),
        15.0, "moderate", "Leaf removal + copper spray."),
}

HEALTHY_CLASSES = tuple(k for k, v in DISEASE_DB.items() if v.pathogen_type == "none")


# PlantVillage class -> app crop name. Used to map CNN output onto the farm's crops.
CLASS_TO_CROP: dict[str, str] = {}
for _k, _v in DISEASE_DB.items():
    CLASS_TO_CROP[_k] = _v.crop

# Classes that matter for a Nashik / Maharashtra farm.
REGIONAL_CLASSES = tuple(
    k for k, v in DISEASE_DB.items()
    if v.crop in {"Tomato", "Maize", "Potato", "Grape", "Bell pepper", "Squash"}
)


def severity_from_confidence(conf: float, weight: float) -> str:
    """Combine model confidence with pathogen aggressiveness into a severity label."""
    if weight <= 0:
        return "healthy"
    score = conf * weight
    if score >= 0.7:
        return "severe"
    if score >= 0.45:
        return "moderate"
    return "mild"


def yield_loss(conf: float, info: DiseaseInfo) -> float:
    """Expected yield loss (%) = base loss scaled by confidence."""
    if info.pathogen_type == "none":
        return 0.0
    return round(info.yield_loss_pct * min(max(conf, 0.0), 1.0), 1)

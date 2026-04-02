# forms/__init__.py
#
# Package-level re-export layer for forms/
#
# PURPOSE: Every form class is re-exported here so that:
#   from ..forms import SomeForm    (inside views/ sub-modules)
# resolves correctly without callers needing to know which sub-module a
# form lives in. This keeps all view imports stable if forms are ever
# reorganized between sub-modules.
#
# SUB-MODULE LAYOUT:
#   forms_core.py          WeatherForm, TextForm (shared across view categories)
#   forms_it_tools.py      CookieAuditForm, FontInspectorForm, XMLUploadForm,
#                          DomainForm, IPForm, SSLCheckForm, SubnetCalculatorForm,
#                          EmailAuthForm, WhoisForm, HttpHeaderForm,
#                          RedirectCheckerForm, JsonLdValidatorForm,
#                          RobotsAnalyzerForm, CronBuilderForm,
#                          EpochToHumanForm, HumanToEpochForm
#   forms_seo_tools.py     SitemapForm, OGPreviewerForm
#   forms_freight_tools.py CarrierSearchForm, FreightClassForm, FuelSurchargeForm,
#                          HOSTripPlannerForm, TieDownForm, CPMCalculatorForm,
#                          LinearFootForm, DetentionFeeForm, WarehouseStorageForm,
#                          PartialRateForm, DeadheadCalculatorForm,
#                          MultiStopSplitterForm, LaneRateAnalyzerForm,
#                          FreightMarginForm
#   forms_glass_tools.py   GlassVolumeForm, KilnScheduleForm, StainedGlassCostForm,
#                          TempConverterForm, RampCalculatorForm,
#                          StainedGlassMaterialsForm, LampworkMaterialForm,
#                          GlassReactionForm, FritMixingForm, CircleCutterForm
#   forms_radio_tools.py   CallsignLookupForm, BandPlanForm, RepeaterFinderForm,
#                          AntennaCalculatorForm, GridSquareForm, RFExposureForm,
#                          CoaxCableLossForm
#   forms_space_tools.py   SatellitePassForm, LunarPhaseCalendarForm,
#                          NightSkyPlannerForm
#   forms_misc.py          QRForm, MonteCarloForm, AITokenCostForm
#
# MAINTENANCE: When you add a new form class to any sub-module, add its name
# to the corresponding import block below AND to __all__.
#
# NEVER put form logic here — this file is a re-export shim only.

from .forms_core import (
    WeatherForm,    # shared: used by both weather view and ISS tracker
    TextForm,       # used by grade_level_analyzer
)

from .forms_it_tools import (
    CookieAuditForm,
    FontInspectorForm,
    XMLUploadForm,
    DomainForm,
    IPForm,
    SSLCheckForm,
    SubnetCalculatorForm,
    EmailAuthForm,
    WhoisForm,
    HttpHeaderForm,
    RedirectCheckerForm,
    JsonLdValidatorForm,
    RobotsAnalyzerForm,
    CronBuilderForm,
    EpochToHumanForm,
    HumanToEpochForm,
)

from .forms_seo_tools import (
    SitemapForm,
    OGPreviewerForm,
)

from .forms_freight_tools import (
    CarrierSearchForm,
    FreightClassForm,
    FuelSurchargeForm,
    HOSTripPlannerForm,
    TieDownForm,
    CPMCalculatorForm,
    LinearFootForm,
    DetentionFeeForm,
    WarehouseStorageForm,
    PartialRateForm,
    DeadheadCalculatorForm,
    MultiStopSplitterForm,
    LaneRateAnalyzerForm,
    FreightMarginForm,
    AccessorialFeeForm,
)

from .forms_glass_tools import (
    GlassVolumeForm,
    KilnScheduleForm,
    StainedGlassCostForm,
    TempConverterForm,
    RampCalculatorForm,
    StainedGlassMaterialsForm,
    LampworkMaterialForm,
    GlassReactionForm,
    FritMixingForm,
    CircleCutterForm,
)

from .forms_radio_tools import (
    CallsignLookupForm,
    BandPlanForm,
    RepeaterFinderForm,
    AntennaCalculatorForm,
    GridSquareForm,
    RFExposureForm,
    CoaxCableLossForm,
)

from .forms_space_tools import (
    SatellitePassForm,
    LunarPhaseCalendarForm,
    NightSkyPlannerForm,
)

from .forms_misc import (
    QRForm,
    MonteCarloForm,
    AITokenCostForm,
    JobFitForm,
)

__all__ = [
    # Core (shared)
    "WeatherForm", "TextForm",
    # IT Tools
    "CookieAuditForm", "FontInspectorForm", "XMLUploadForm",
    "DomainForm", "IPForm", "SSLCheckForm",
    "SubnetCalculatorForm", "EmailAuthForm", "WhoisForm",
    "HttpHeaderForm", "RedirectCheckerForm", "JsonLdValidatorForm",
    "RobotsAnalyzerForm", "CronBuilderForm", "EpochToHumanForm", "HumanToEpochForm",
    # SEO Tools
    "SitemapForm", "OGPreviewerForm",
    # Freight Tools
    "CarrierSearchForm", "FreightClassForm", "FuelSurchargeForm",
    "HOSTripPlannerForm", "TieDownForm", "CPMCalculatorForm",
    "LinearFootForm", "DetentionFeeForm", "WarehouseStorageForm",
    "PartialRateForm", "DeadheadCalculatorForm", "MultiStopSplitterForm",
    "LaneRateAnalyzerForm", "FreightMarginForm","AccessorialFeeForm",
    # Glass Tools
    "GlassVolumeForm", "KilnScheduleForm", "StainedGlassCostForm",
    "TempConverterForm", "RampCalculatorForm", "StainedGlassMaterialsForm",
    "LampworkMaterialForm", "GlassReactionForm", "FritMixingForm", "CircleCutterForm",
    # Radio Tools
    "CallsignLookupForm", "BandPlanForm", "RepeaterFinderForm",
    "AntennaCalculatorForm", "GridSquareForm", "RFExposureForm", "CoaxCableLossForm",
    # Space Tools
    "SatellitePassForm", "LunarPhaseCalendarForm", "NightSkyPlannerForm",
    # Misc
    "QRForm", "MonteCarloForm", "AITokenCostForm", "JobFitForm",
]
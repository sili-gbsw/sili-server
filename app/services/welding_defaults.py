"""Default welding config seed values.

Source: docs/v1_아이디어_구체화.md 15절 (config.json 구조 예시).
Loaded on first GET /api/v1/config when no document exists yet.
"""

DEFAULT_WELDING_CONFIG: dict = {
    "thickness_limits": {
        "0.6+0.6": {"I_min": 6.5, "I_max": 8.0,  "T_min": 8,  "T_max": 10, "F_min": 1.5, "F_max": 2.0},
        "0.8+0.8": {"I_min": 7.5, "I_max": 9.0,  "T_min": 9,  "T_max": 12, "F_min": 1.8, "F_max": 2.5},
        "0.8+1.2": {"I_min": 8.5, "I_max": 10.5, "T_min": 10, "T_max": 14, "F_min": 2.2, "F_max": 3.0},
        "1.0+1.0": {"I_min": 9.0, "I_max": 11.0, "T_min": 11, "T_max": 15, "F_min": 2.5, "F_max": 3.2},
        "1.2+1.2": {"I_min": 9.5, "I_max": 11.5, "T_min": 12, "T_max": 16, "F_min": 2.8, "F_max": 3.8},
        "1.5+1.5": {"I_min": 10.5, "I_max": 12.5, "T_min": 14, "T_max": 18, "F_min": 3.5, "F_max": 4.5},
        "2.0+2.0": {"I_min": 11.5, "I_max": 13.5, "T_min": 16, "T_max": 22, "F_min": 4.5, "F_max": 5.5},
    },
    "material_profiles": {
        "MILD":  {"current_factor": 1.00, "time_factor": 1.00, "force_factor": 1.00},
        "HSLA":  {"current_factor": 1.02, "time_factor": 1.05, "force_factor": 1.07},
        "DP600": {"current_factor": 0.97, "time_factor": 1.10, "force_factor": 1.15},
        "DP980": {"current_factor": 0.92, "time_factor": 1.15, "force_factor": 1.25},
        "UHSS":  {"current_factor": 0.88, "time_factor": 0.92, "force_factor": 1.25},
        "GA":    {"current_factor": 1.12, "time_factor": 1.14, "force_factor": 1.05},
        "GI":    {"current_factor": 1.15, "time_factor": 1.18, "force_factor": 1.05},
    },
    "quality_class_tolerance": {
        "A": {"thin": 0.14, "thick": 0.15},
        "B": {"thin": 0.17, "thick": 0.15},
        "C": {"thin": 0.20, "thick": 0.17},
    },
    "electrode_shape_rule": {
        "thin_threshold_mm": 3.2,
        "below": "C-TYPE",
        "above_or_equal": "R-TYPE",
    },
    "thickness_ratio_limit": 3.0,
    "electrode_wear_limit": {
        "caution_hits": 1500,
        "reject_hits":  2000,
    },
    "min_pitch_mm": {
        "0.6": 6,  "0.8": 12, "1.0": 18, "1.2": 20,
        "1.4": 23, "1.6": 27, "1.8": 31, "2.0": 35,
        "2.4": 40, "2.8": 45, "3.2": 50, "4.0": 67, "5.0": 89,
    },
    "min_lap_mm": {
        "0.6": 10, "0.8": 11, "1.0": 12, "1.2": 14,
        "1.4": 15, "1.6": 16, "1.8": 17, "2.0": 18,
        "2.4": 20, "2.8": 21, "3.2": 22, "4.0": 32, "5.0": 45,
    },
    "alert_sound_enabled": True,
    "alert_visual_enabled": True,
}

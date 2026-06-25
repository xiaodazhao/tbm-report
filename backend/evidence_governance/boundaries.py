from __future__ import annotations


METRIC_BOUNDARIES = {
    "RAI": {
        "meaning": "construction response attention",
        "forbidden": ["risk probability", "disaster probability", "forward risk"],
    },
    "GRS": {
        "meaning": "geological evidence attention",
        "forbidden": ["disaster probability", "ground truth geological condition"],
    },
    "GRCI": {
        "meaning": "excavated-scope geology-response coupling attention",
        "forbidden": ["disaster probability", "forward risk probability", "causal proof"],
    },
    "cutterhead_power_proxy": {
        "meaning": "relative cutterhead load proxy",
        "forbidden": ["true physical power", "energy", "geological hazard proof"],
    },
    "thrust_per_penetration": {
        "meaning": "load-penetration response proxy",
        "forbidden": ["strict specific energy", "geological hazard proof"],
    },
    "torque_per_penetration": {
        "meaning": "load-penetration response proxy",
        "forbidden": ["strict specific energy", "geological hazard proof"],
    },
}

PROXY_BOUNDARIES = {
    "plc_enhanced_metrics": (
        "PLC enhanced metrics are excavated-scope construction response evidence only; "
        "they do not independently indicate geological risk or forward ground conditions."
    ),
    "cutterhead_power_proxy": "Proxy only; do not describe as true power or kW without unit calibration.",
    "thrust_per_penetration": "Proxy only; do not describe as strict specific energy.",
    "torque_per_penetration": "Proxy only; do not describe as strict specific energy.",
}

FORWARD_BOUNDARIES = [
    "forward_attention is an attention/indication role, not an occurred fact role",
    "forward_attention must not use GRCI",
    "excavated PLC response must not be used as proof of forward geological condition",
]

GRCI_BOUNDARIES = [
    "GRCI is not a disaster probability",
    "GRCI is not a forward risk probability",
    "GRCI is available only for daily_review cells with both GRS and RAI evidence",
]

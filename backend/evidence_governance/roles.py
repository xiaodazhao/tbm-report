from __future__ import annotations


ROLE_RULES = {
    "daily_review": {
        "can_use": [
            "RAI",
            "GRS",
            "GRCI if available",
            "PLC enhanced metrics",
            "excavated-scope geology evidence",
            "daily-scope gas evidence",
        ],
        "cannot_claim": [
            "forward geological fact",
            "disaster probability",
            "risk probability",
            "PLC proves geology",
        ],
    },
    "forward_attention": {
        "can_use": [
            "forward geological evidence",
            "GRS as geological evidence attention",
            "source_trace",
            "forward_profile",
        ],
        "cannot_use": [
            "GRCI",
            "high_grci_cells",
            "PLC enhanced metrics as forward fact",
            "RAI as forward risk",
            "excavated PLC response as proof of forward condition",
        ],
    },
    "local_background": {
        "can_use": [
            "adjacent/background evidence",
            "context explanation",
        ],
        "cannot_claim": [
            "current daily conclusion",
            "forward fact",
            "high risk conclusion",
        ],
    },
}

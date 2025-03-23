from enum import Enum, unique


@unique
class ReportStatus(Enum):
    QUEUE = ("queue", "In Queue")
    NEEDS_REVIEW = ("needs_review", "Needs Review")
    IN_REVIEW = ("in_review", "Analyst Reviewing")
    COMPLETED = ("completed", "Completed")

    # For each tuple above, set the value and display name as two separate properties
    def __new__(cls, val: str, display: str):
        obj = object.__new__(cls)
        obj._value_ = val
        obj.display_name = display
        return obj


@unique
class AssociationWith(Enum):
    CA = "category"
    CN = "country"
    RG = "region"
    GR = "group"

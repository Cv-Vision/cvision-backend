from enum import Enum

class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"

class ExperienceLevel(str, Enum):
    JUNIOR = "JUNIOR"
    SEMISENIOR = "SEMISENIOR"
    SENIOR = "SENIOR"

class EnglishLevel(str, Enum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    NATIVE = "NATIVE"
    NOT_REQUIRED = "NOT_REQUIRED"

class ContractType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    FREELANCE = "FREELANCE"
    INTERNSHIP = "INTERNSHIP"
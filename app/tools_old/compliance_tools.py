from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.serialization import clean_for_json


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _read_csv(filename: str, **kwargs: Any) -> pd.DataFrame:
    path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    return pd.read_csv(
        path,
        encoding="utf-8-sig",
        **kwargs,
    )


def get_apparel_product(sku: str) -> dict:
    """Return one apparel product from Product_Catalog.csv."""

    products = _read_csv(
        "Product_Catalog.csv",
        dtype={"sku": str, "hs6_reference": str},
    )

    products["sku"] = (
        products["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    normalized_sku = sku.strip().upper()

    match = products[products["sku"] == normalized_sku]

    if match.empty:
        return {
            "success": False,
            "error": f"Apparel SKU {normalized_sku} was not found.",
        }

    return clean_for_json({
        "success": True,
        "product": match.iloc[0].to_dict(),
    })


def get_product_compliance_checks(sku: str) -> dict:
    """Return all compliance evidence checks applicable to a SKU."""

    checks = _read_csv(
        "SKU_Compliance_Checks.csv",
        dtype={
            "sku": str,
            "rule_id": str,
            "evidence_type_id": str,
        },
    )

    checks["sku"] = (
        checks["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    normalized_sku = sku.strip().upper()

    matches = checks[
        (checks["sku"] == normalized_sku)
        & (
            checks["applicable"]
            .astype(str)
            .str.strip()
            .str.lower()
            == "yes"
        )
    ].copy()

    if matches.empty:
        return {
            "success": True,
            "check_count": 0,
            "checks": [],
        }

    return clean_for_json({
        "success": True,
        "check_count": len(matches),
        "checks": matches.to_dict(orient="records"),
    })


def get_compliance_rules(rule_ids: list[str]) -> dict:
    """Return compliance rule definitions for the supplied rule IDs."""

    rules = _read_csv(
        "Compliance_Rules.csv",
        dtype={"rule_id": str},
    )

    normalized_ids = {
        str(rule_id).strip().upper()
        for rule_id in rule_ids
    }

    rules["rule_id"] = (
        rules["rule_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = rules[rules["rule_id"].isin(normalized_ids)].copy()

    return clean_for_json({
        "success": True,
        "rule_count": len(matches),
        "rules": matches.to_dict(orient="records"),
    })


def evaluate_apparel_compliance(sku: str) -> dict:
    """Evaluate synthetic compliance evidence for one apparel SKU."""

    product_result = get_apparel_product(sku)

    if not product_result["success"]:
        return product_result

    checks_result = get_product_compliance_checks(sku)

    if not checks_result["checks"]:
        return {
            "success": True,
            "sku": sku.strip().upper(),
            "decision": "REVIEW_REQUIRED",
            "blocking_issues": [],
            "review_items": [],
            "warnings": [],
            "passed_rules": [],
            "message": "No compliance checks were found for this SKU.",
        }

    rule_ids = [
        check["rule_id"]
        for check in checks_result["checks"]
    ]

    rules_result = get_compliance_rules(rule_ids)

    rules_by_id = {
        rule["rule_id"]: rule
        for rule in rules_result["rules"]
    }

    blocking_issues = []
    review_items = []
    warnings = []
    passed_rules = []
    information = []

    for check in checks_result["checks"]:
        rule_id = check["rule_id"]
        rule = rules_by_id.get(rule_id, {})
        effect = str(check.get("decision_effect", "")).upper()

        result = {
            "rule_id": rule_id,
            "rule_group": rule.get("rule_group"),
            "requirement": rule.get("requirement"),
            "evidence_status": check.get("evidence_status"),
            "evidence_type_id": check.get("evidence_type_id"),
            "source_url": rule.get("source_url"),
            "message": check.get("expected_agent_message"),
        }

        if effect == "BLOCK":
            blocking_issues.append(result)
        elif effect == "REVIEW":
            review_items.append(result)
        elif effect == "WARNING":
            warnings.append(result)
        elif effect == "PASS":
            passed_rules.append(result)
        else:
            information.append(result)

    if blocking_issues:
        decision = "BLOCKED"
    elif review_items:
        decision = "REVIEW_REQUIRED"
    else:
        decision = "COMPLIANT_FOR_CURRENT_STAGE"

    next_actions = []

    for issue in blocking_issues:
        next_actions.append(
            f"Resolve {issue['rule_id']}: "
            f"{issue.get('requirement')}"
        )

    for issue in review_items:
        next_actions.append(
            f"Verify evidence for {issue['rule_id']}."
        )

    return clean_for_json({
        "success": True,
        "sku": sku.strip().upper(),
        "product": product_result["product"],
        "decision": decision,
        "blocking_issues": blocking_issues,
        "review_items": review_items,
        "warnings": warnings,
        "passed_rules": passed_rules,
        "information": information,
        "next_actions": next_actions,
        "disclaimer": (
            "Synthetic evidence assessment for software testing. "
            "Not a legal compliance determination."
        ),
    })
"""All money values use the same currency (INR in demo). No imputed ratios."""
import math


def emi(principal, annual_rate, months):
    if principal <= 0 or months <= 0 or annual_rate is None:
        return None
    if annual_rate == 0:
        return round(principal / months, 2)
    r = annual_rate / 1200
    return round(principal * r / (1 - (1 + r) ** (-months)), 2)


def financial_features(app):
    p = app.profile
    income = p.get('monthly_income') if p.get('income_verified') and not p.get('income_conflict') else None
    debt = p.get('monthly_debt')
    expenses = p.get('monthly_expenses')
    payment = emi(app.amount, app.annual_rate, app.tenure_months)
    return {
        'monthly_income': income, 'monthly_debt': debt, 'monthly_expenses': expenses,
        'dti': round(debt / income * 100, 2) if income and debt is not None else None,
        'lti': round(app.amount / (income * 12), 3) if income else None,
        'ltv': round(app.amount / p['asset_value'] * 100, 2) if p.get('asset_value') and p.get('asset_verified') else None,
        'emi': payment,
        'disposable_income': round(income - debt - expenses - payment, 2) if income is not None and debt is not None and expenses is not None and payment is not None else None,
        'repayment_burden': round((debt + payment) / income * 100, 2) if income and debt is not None and payment is not None else None,
        'assumptions': ['Monthly gross income must be reviewed as verified.', 'DTI excludes the proposed EMI; repayment burden includes it.', 'Annual income = monthly gross income × 12.', 'Rate is an explicit illustration input, not an offer.', 'Asset value must be verified by the reviewer before use.'],
        'currency': 'INR',
    }

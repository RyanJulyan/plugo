def calculate_monthly_investment_from_interest_earned(
    monthly_expense: float,
    annual_interest_rate: float,
    inflation_rate: float,
):
    """
    Calculate the total investment needed to support a given monthly expense, accounting for inflation.

    Args:
        monthly_expense (float): The monthly expense amount.
        annual_interest_rate (float): The annual interest rate as a percentage (e.g., 8 for 8%).
        inflation_rate (float): The annual inflation rate as a percentage (e.g., 3 for 3%).

    Returns:
        float: The total investment amount needed.
    """
    # Calculate the real annual interest rate adjusted for inflation
    real_annual_interest_rate = (
        (1 + annual_interest_rate) / (1 + inflation_rate) - 1
    ) * 100
    # Convert the real annual interest rate to a monthly rate
    monthly_interest_rate = real_annual_interest_rate / 12 / 100
    # Calculate total investment needed
    total_investment = monthly_expense / monthly_interest_rate

    return total_investment


# Example usage
monthly_expense = 8000
annual_interest_rate = 0.08
inflation_rate = 0.05  # Assuming an inflation rate of 5%
investment_needed = calculate_monthly_investment_from_interest_earned(
    monthly_expense, annual_interest_rate, inflation_rate
)
print(f"The total investment needed is ${investment_needed:,.2f}")

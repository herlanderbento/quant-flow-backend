from shared.domain.exceptions import InvalidArgumentException


def calculate_order_quantity(allocated_capital: float, current_price: float) -> float:
    allocated_capital = float(allocated_capital)
    current_price = float(current_price)
    if allocated_capital <= 0:
        raise InvalidArgumentException("allocated_capital must be greater than zero.")
    if current_price <= 0:
        raise InvalidArgumentException("current_price must be greater than zero.")
    return allocated_capital / current_price

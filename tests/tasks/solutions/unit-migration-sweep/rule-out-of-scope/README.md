# shipcalc

Order weight and shipping cost calculator.

    python -m shipcalc show samples/order.json
    python -m shipcalc add samples/order.json LAMP-3 2400 1
    python -m shipcalc quote samples/order.json --zone eu

Weights are given in kilograms. The package API is documented in the module docstrings.

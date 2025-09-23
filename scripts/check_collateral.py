"""Check collateral discrepancy."""

positions = [
    {'symbol': 'ASTERUSDT', 'qty': 79.31, 'price': 2.0332, 'leverage': 10}
]

total_collateral = 0
for pos in positions:
    position_value = pos['qty'] * pos['price']
    collateral = position_value / pos['leverage']
    print(f'{pos["symbol"]}: Position value=${position_value:.2f}, Collateral=${collateral:.2f}')
    total_collateral += collateral

print(f'Total collateral should be: ${total_collateral:.2f}')
print(f'But system shows: $196.43')
print(f'Difference: ${196.43 - total_collateral:.2f}')
print()
print('This suggests multiple positions or incorrect accumulation of collateral values.')
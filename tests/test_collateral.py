"""Test collateral calculation for position manager."""

# Example from your log:
# ASTERUSDT    LONG    79.3100    $2.0332    $39    -6.88%    $15.09    10x

position_quantity = 79.31
mark_price = 2.0332
leverage = 10

# Calculate position value (notional)
position_value = position_quantity * mark_price
print(f"Position value (notional): {position_value:.2f} USDT")

# Calculate collateral (margin)
collateral = position_value / leverage
print(f"Collateral (margin used): {collateral:.2f} USDT")

# Your position shows $15.09 collateral which is close to our calculation
print(f"Expected collateral from dashboard: $15.09")

# Now test with the limit check
max_total_collateral = 200.0
current_collateral = 196.43  # From your log
pending_collateral = 3.00    # From your log

# New trade would add
new_trade_value = 10.00  # trade_value_usdt from settings
new_trade_leverage = 10
new_trade_collateral = new_trade_value / new_trade_leverage

print(f"\nPosition limit check:")
print(f"Current collateral: ${current_collateral:.2f}")
print(f"Pending collateral: ${pending_collateral:.2f}")
print(f"New trade collateral: ${new_trade_collateral:.2f}")

total_after_new = current_collateral + pending_collateral + new_trade_collateral
print(f"Total after new trade: ${total_after_new:.2f}")
print(f"Max allowed: ${max_total_collateral:.2f}")

if total_after_new > max_total_collateral:
    print(f"❌ Would exceed limit by ${total_after_new - max_total_collateral:.2f}")
else:
    print(f"✓ Within limits with ${max_total_collateral - total_after_new:.2f} remaining")
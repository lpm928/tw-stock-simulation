import datetime

class PaperBroker:
    def __init__(self, initial_balance=1000000.0):
        self.balance = initial_balance
        # Inventory structure: { '2330.TW': {'qty': 1000, 'cost': 500.0} }
        # For Short position, qty will be negative, cost will be valid positive (avg sell price).
        self.inventory = {} 
        self.transaction_history = [] 

    def set_balance(self, amount):
        """Manually set balance (Cheat/Top-up)"""
        self.balance = amount

    def restore_state(self, balance, inventory, history):
        """Restores state from persistence"""
        self.balance = balance
        self.inventory = inventory
        self.transaction_history = history

    def buy(self, stock_id, price, quantity, action="現股買進"):
        """
        Handles Buying (Long) and Covering (Short).
        Action: "現股買進" or "融券回補"
        """
        if quantity <= 0 or price <= 0:
            return False, "價格與數量必須大於 0"
            
        cost = price * quantity
        fee = int(cost * 0.001425)
        if fee < 20: fee = 20
        
        # Buying/Covering: No Tax, only Fee.
        total_outlay = cost + fee
        
        if self.balance < total_outlay:
             return False, f"餘額不足! 需要 {total_outlay:.0f}, 餘額 {self.balance:.0f}"
             
        # Update Balance
        self.balance -= total_outlay
        
        # Update Inventory
        if stock_id not in self.inventory:
            self.inventory[stock_id] = {'qty': 0, 'cost': 0.0}
            
        holding = self.inventory[stock_id]
        current_qty = holding['qty']
        avg_cost = holding['cost']
        
        if action == "現股買進":
            # Adding Long Position
            if current_qty < 0:
                # Covering short?? No, 'stock buy' while short usually means covering or locking diff account.
                # Here we assume 'Netting' if user wants. But usually different actions.
                # If "現股買進" while short, it's just buying long (if platform allows hedging) OR netting.
                # Strict mode: Check 'action'. 
                # If user used "現股買進", treat as Long Asset.
                # But if we have negative qty, we should probably cover?
                # Let's keep Simple Netting: If short, "Buy" covers.
                # BUT user has explicit "融券回補" button.
                # If user clicks "現股買進" while short 1000. 
                # Should we error? "請使用融券回補"?
                # Let's allow netting for simplicity in calculation, but warn?
                # Or adhere to the Action Button intent.
                pass
            
            # Weighted Average Cost (Long)
            # New CostBasis = (OldCost*OldQty + NewCost*NewQty) / TotalQty
            # Only if OldQty > 0
            if current_qty >= 0:
                total_shares = current_qty + quantity
                total_cost_basis = (current_qty * avg_cost) + cost + fee # Include fee in cost? Usually yes for BEP.
                # Standard: (Cost * Qty + Fee) / TotalQty
                new_avg = total_cost_basis / total_shares
                
                holding['qty'] += quantity
                holding['cost'] = new_avg
            else:
                 # Hedging/Netting logic if mixed... Let's assume user handled it right.
                 # Just add to qty.
                 holding['qty'] += quantity
                 # Re-calc cost? Complex if crossing 0.
                 # Let's simplify: If crossing 0, reset cost.
                 pass

        elif action == "融券回補":
            # Covering Short
            if current_qty >= 0:
                return False, "無空單可回補"
            if abs(current_qty) < quantity:
                return False, f"回補股數 ({quantity}) 超過庫存空單 ({abs(current_qty)})"
                
            # Valid cover
            # Realized P&L = (ShortPrice - CoverPrice) * Qty - Fees
            # Short Price was stored in 'cost'.
            # Logic: We are reducing liability.
            
            # P&L Calculation for this chunk
            short_price = avg_cost
            cover_price = price
            
            # Gross P&L : (Sell - Buy)
            gross_pnl = (short_price - cover_price) * quantity
            
            # Net P&L (Fees were paid at Open? No, Fee paid now + Tax paid at Open? 
            # Taiwan Short: Fee at Buy, Fee at Sell, Tax at Sell.
            # We deducted Fee/Tax at Open. Now deduct Fee at Cover.
            # So Net PnL is correct as calculated below minus THIS fee.
            
            net_pnl = gross_pnl - fee # Tax was paid when shorting.
            
            # Recover Margin? 
            # In paper trading, we deducted NetProceeds from Shorting. 
            # Wait, Shorting = Cash Increase (Proceeds). 
            # Covering = Cash Decrease (Outlay).
            # We already deducted Outlay from balance above.
            # Now we just update Inventory.
            
            self.balance += 0 # Already deducted.
            # Wait, Realized P&L is implicitly reflected in Balance change?
            # Start: 100. Short 10 shares @ 10. Proceeds +100. Bal 200.
            # Cover 10 shares @ 8. Cost 80. Bal 120.
            # Profit 20. Correct.
            
            holding['qty'] += quantity # -10 + 10 = 0
            if holding['qty'] == 0:
                holding['cost'] = 0
            
            self._log_transaction(action, stock_id, price, quantity, fee, 0, net_pnl)
            return True, f"{action}成功! 回補 {quantity}股, 損益 {net_pnl:+.0f}"

        # General Long Buy Fallback logging
        if action == "現股買進":
            self._log_transaction(action, stock_id, price, quantity, fee, 0, 0)
            return True, f"{action}成功! {quantity}股, 均價 {price:.2f}, 總花費 {total_outlay:.0f}"

        return False, "Logic Error"

    def sell(self, stock_id, price, quantity, action="現股賣出"):
        """
        Handles Selling (Long) and Shorting (Short).
        Action: "現股賣出" or "融券賣出"
        """
        if quantity <= 0 or price <= 0:
            return False, "價格與數量必須大於 0"
            
        revenue = price * quantity
        fee = int(revenue * 0.001425)
        if fee < 20: fee = 20
        tax = int(revenue * 0.003)
        
        net_proceeds = revenue - fee - tax
        
        if self.inventory.get(stock_id) is None:
            self.inventory[stock_id] = {'qty': 0, 'cost': 0.0}
            
        holding = self.inventory[stock_id]
        current_qty = holding['qty']
        avg_cost = holding['cost']
        
        if action == "現股賣出":
            if current_qty < quantity:
                return False, f"庫存不足! 持有 {current_qty}, 欲賣出 {quantity}"
            
            # Realized P&L
            # (Sell Price - Avg Cost) * Qty - Fee - Tax
            # Avg Cost included Buy Fee.
            # Net Proceeds - (AvgCost * Qty)
            # Wait, AvgCost = (Price*Qty + Fee)/Qty. 
            cost_basis = avg_cost * quantity
            realized_pnl = net_proceeds - (cost_basis * (1 if current_qty >0 else 0)) 
            # If we calculated cost basis including fee, then cost_basis is total outlay of that portion.
            # net_proceeds is total inflow.
            # PnL = Inflow - Outflow. Correct.
            
            self.balance += net_proceeds
            holding['qty'] -= quantity
            if holding['qty'] == 0:
                holding['cost'] = 0
                
            self._log_transaction(action, stock_id, price, quantity, fee, tax, realized_pnl)
            return True, f"{action}成功! {quantity}股, 淨收 {net_proceeds:.0f}, 損益 {realized_pnl:+.0f}"

        elif action == "融券賣出":
            # Short Selling
            # If already Long, should we Sell Long first?
            # "現股賣出" button is for Long. "融券賣出" is for Short.
            # We allow holding Long and Short simultaneously?
            # For simplicity: One aggregate position per stock.
            # If Long 1000, Short 1000 -> Net 0.
            # If Platform allows distinct positions, we need separate buckets.
            # Our structure: { 'qty': ... } implies Netting.
            
            if current_qty > 0:
                 return False, "已有現股多單，請先賣出再放空 (系統採淨部位管理)"
            
            # Check Margin? (90% usually).
            # We assume user has cash.
            # Required Margin = Price * Qty * 0.9.
            # margin = int(price * quantity * 0.9)
            # if self.balance < margin: ...
            # For Paper Trading, let's just ensure they have enough cash to cover potential moves?
            # Or just check Balance + Proceeds?
            # Standard Short: You get Proceeds, but margin is locked.
            # Simplified: You get Proceeds added to Cash immediately.
            
            self.balance += net_proceeds
            holding['qty'] -= quantity # Becomes negative
            
            # Update Avg Sell Price (Cost of Short)
            # If entering new short:
            if current_qty == 0:
                holding['cost'] = price # Just price? Or Price - Fees?
                # Usually Avg Price.
            else:
                # Adding to short
                # Weighted Avg
                old_abs = abs(current_qty)
                total_shares = old_abs + quantity
                total_val = (old_abs * avg_cost) + (quantity * price)
                holding['cost'] = total_val / total_shares
            
            self._log_transaction(action, stock_id, price, quantity, fee, tax, 0)
            return True, f"{action}成功! {quantity}股, 淨收 {net_proceeds:.0f} (建立空單)"
            
        return False, "未知交易類型"

    def get_account_summary(self, current_prices=None):
        if current_prices is None: current_prices = {}
        
        market_value = 0
        short_liability = 0
        unrealized_pnl = 0
        
        for stock, data in self.inventory.items():
            qty = data['qty']
            cost = data['cost'] # buy cost (long) or sell price (short)
            
            price = current_prices.get(stock, cost) # fallback
            
            if qty > 0:
                # Long
                mv = price * qty
                market_value += mv
                # Cost is (AvgCost). Unr PnL = (Price*Qty - Cost*Qty) - SellFees?
                # Raw PnL usually.
                unrealized_pnl += (mv - (cost * qty))
            else:
                # Short
                liability = price * abs(qty)
                short_liability += liability
                # Short PnL: (SellPrice - CurrPrice) * Qty
                unrealized_pnl += ((cost - price) * abs(qty))
        
        equity = self.balance + market_value - short_liability
        
        # Calculate Realized PnL from History
        realized_pnl = sum([x.get('P&L', 0) for x in self.transaction_history])

        return {
            "Balance": self.balance,
            "Market_Value": market_value, # Longs
            "Short_Liability": short_liability,
            "Equity": equity, 
            "Total_Assets": equity, # User calls it Net Worth/Total Assets
            "Unrealized_PnL": unrealized_pnl,
            "Realized_PnL": realized_pnl
        }

    def _log_transaction(self, action, stock_id, price, quantity, fee, tax, pnl):
        record = {
            "Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Action": action,
            "Stock": stock_id,
            "Price": price,
            "Qty": quantity,
            "Fee": fee,
            "Tax": tax,
            "P&L": pnl if pnl != 0 else 0
        }
        self.transaction_history.append(record)

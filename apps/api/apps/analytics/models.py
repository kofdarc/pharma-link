# Analytics is a read-only projection over inventory, sales, orders and demand signals.
# It owns no tables on purpose: no aggregate can drift out of sync with the ledger it
# summarises. UnmetDemandSignal lives in apps.orders because that is where it is written.

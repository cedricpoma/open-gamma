from tastytrade.instruments import NestedOptionChain, OptionChain
from tastytrade import Session

print("NestedOptionChain methods:", dir(NestedOptionChain))
try:
    print("OptionChain methods:", dir(OptionChain))
except:
    print("OptionChain not found")

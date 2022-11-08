"""Transaction options."""
from typing import NewType

Level = NewType("transactionDetails", str)

Full = Level("full")
Accounts = Level("accounts")
Signatures = Level("signatures")
_None = Level("none")

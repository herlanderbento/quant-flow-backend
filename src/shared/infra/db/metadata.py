# Import all models here directly
from shared.infra.db.database import Base
from account.infra.db.sql_models import Base as AccountBase  # noqa: F401  registers the models
from trader.infra.db.sql_models import Base as TraderBase  # noqa: F401  registers the models
from wallet.infra.db.sql_models import Base as WalletBase  # noqa: F401  registers the models
target_metadata = Base.metadata  # defined here
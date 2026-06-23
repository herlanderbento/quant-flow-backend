# Import all models here directly
from shared.infra.db.database import Base
from account.infra.db.sql_models import Base as AccountBase 
from trader.infra.db.sql_models import Base as TraderBase   
from wallet.infra.db.sql_models import Base as WalletBase   

target_metadata = Base.metadata  # defined here
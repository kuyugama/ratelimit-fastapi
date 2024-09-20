# _#_ ratelimit-fastapi

Library allows to easily create fastapi endpoints protected by ratelimit


Here is a basic example:
```python
from datetime import timedelta
import random

from ratelimit.ranking.redis import RedisRanking
from fastapi import FastAPI, Depends, Request
from ratelimit.store.redis import RedisStore
from redis.asyncio import Redis

from ratelimit import (
    RateLimitErrorResponse,
    setup_ratelimit,
    ratelimit,
    LimitRule,
    BaseUser,
)

# Setup redis connection
redis = Redis.from_url("redis://localhost:6379/1")


# Define user model that will be stored by library. This data is stored for
# determining user's rank
class User(BaseUser):
    address: str

    # Unique id is required to be defined, and it must be unique for each user
    @property
    def unique_id(self):
        return self.address


# Define authentication function, here you need to create instance of a model.
# This function is used as a dependency, so it can use all dependencies, that
# can be used in FastAPI
def auth_func(request: Request):
    return User(address=request.client.host, group="user")


app = FastAPI()

# Setup ratelimit
setup_ratelimit(
    app,
    ranking=RedisRanking(redis, User),  # Ranking stores user's ranks
    store=RedisStore(redis),  # Store stores endpoint related data
    authentication_func=auth_func,  # Register authentication function
)


@app.get(
    "/",
    dependencies=[
        Depends(
            ratelimit(  # Create ratelimiting dependency
                LimitRule(  # Define ratelimiting rule
                    hits=120,  # Max 120 requests
                    batch_time=timedelta(
                        minutes=1
                    ).total_seconds(),  # Per 1 minute
                    block_time=timedelta(minutes=5).total_seconds(), # Time to block user for
                ),
                LimitRule(  # Here can be multiple levels of the limiting rules, named "ranks"
                    hits=120,
                    batch_time=timedelta(minutes=1).total_seconds(),
                    block_time=timedelta(minutes=10).total_seconds(),
                ),
                (  # And rules can be grouped to be in one rank
                    LimitRule(
                        hits=120,
                        batch_time=timedelta(minutes=1).total_seconds(),
                        block_time=timedelta(minutes=5).total_seconds(),
                    ),
                    LimitRule(
                        delay=timedelta(
                            seconds=15
                        ).total_seconds(),  # This rule may allow access only if between requests are delay in 15 seconds or more
                        block_time=timedelta(minutes=1).total_seconds(),
                    ),
                ),
            )
        )
    ],
    responses={
        429: {"model": RateLimitErrorResponse}
    },  # Set response model, to see the correct error schema
)
# Define endpoint as usual
def home(a: int = 10, b: int = 30):
    if a > b:
        a, b = b, a

    if a == b:
        a, b = 10, 30

    return {"random_value": random.randint(a, b)}

```

More examples at "examples" directory :3
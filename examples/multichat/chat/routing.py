from channels import route
from .consumers import ChatConsumers

# There's no path matching on these routes; we just rely on the matching
# from the top-level routing. We _could_ path match here if we wanted.
routing = [
    ChatConsumers.as_routes()
]

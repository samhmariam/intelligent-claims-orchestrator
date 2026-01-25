from icpa.orchestration.agent_wrapper import handler as agent_handler
from icpa.orchestration.hitl_callback_lambda import handler as hitl_callback_handler_fn
from icpa.orchestration.notification_lambda import handler as notification_handler_fn
from icpa.orchestration.router_lambda import handler as router_handler_fn
from icpa.orchestration.summarization_lambda import handler as summarization_handler_fn
from icpa.orchestration.terminal_state_lambda import handler as terminal_state_handler_fn


def handler(event, context):
    return agent_handler(event, context)


def summarization_handler(event, context):
    return summarization_handler_fn(event, context)


def router_handler(event, context):
    return router_handler_fn(event, context)


def notification_handler(event, context):
    return notification_handler_fn(event, context)


def terminal_state_handler(event, context):
    return terminal_state_handler_fn(event, context)


def hitl_callback_handler(event, context):
    return hitl_callback_handler_fn(event, context)

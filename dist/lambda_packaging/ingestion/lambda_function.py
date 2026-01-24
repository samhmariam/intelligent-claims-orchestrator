from icpa.ingestion.handlers import (
    ingestion_handler,
    textract_result_handler,
    transcribe_postprocess_handler,
)

def handler(event, context):
    return ingestion_handler(event, context)

def textract_handler(event, context):
    return textract_result_handler(event, context)

def transcribe_handler(event, context):
    return transcribe_postprocess_handler(event, context)

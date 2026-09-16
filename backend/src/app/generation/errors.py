class GenerationFailure(Exception):
    """Provider/network error, or provider output that fails schema
    validation or citation/provenance grounding validation.

    Must never be swallowed into a 200 business answer (e.g.
    "insufficient_evidence") — a caller (the router) is required to turn
    this into a 502. This is the boundary between "the model honestly
    found no evidence" (a successful abstention) and "the model produced
    an ungrounded or malformed answer" (an infrastructure/generation
    failure), which are not the same outcome.
    """

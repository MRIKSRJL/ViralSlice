class PipelineError(Exception):
    """Erreur attendue du pipeline, dont le message est affiché à l'utilisateur."""


class LLMResponseError(PipelineError):
    pass


class FFmpegError(PipelineError):
    pass

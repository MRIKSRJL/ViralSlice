import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_example_env_file_loads_with_optional_paths_unset():
    settings = Settings(_env_file=".env.example")
    assert settings.ytdlp_cookies_file is None
    assert settings.fonts_dir is None
    assert settings.original_volume_with_voiceover == 0.22


@pytest.mark.parametrize("volume", [0.1, 0.5])
def test_original_volume_must_stay_between_20_and_25_percent(volume):
    with pytest.raises(ValidationError):
        Settings(original_volume_with_voiceover=volume)

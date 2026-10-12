"""`python -m pitstudio_pipeline.surrogates.gns <train|evaluate|export|speed> ...` (see `stages`)."""

import sys

from pitstudio_pipeline.surrogates.gns.stages import main

sys.exit(main())

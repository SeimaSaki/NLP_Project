#!/usr/bin/env python
import logging
import os
import sys

if os.environ.get('ALLENNLP_DEBUG'):
    LEVEL = logging.DEBUG
else:
    LEVEL = logging.INFO

sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir))))
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
                    level=LEVEL)

# pylint: disable=wrong-import-position
from allennlp.commands import main
from kglm.commands import CompleteTheSentence

if __name__ == "__main__":
    main(prog="allennlp",
         subcommand_overrides={
             'complete-the-sentence': CompleteTheSentence(),
         })

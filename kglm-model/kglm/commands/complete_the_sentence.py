"""
For running complete the sentence experiments.
"""
from typing import List, Iterator, Optional
import argparse
import sys
import json

import inspect

from allennlp.commands.subcommand import Subcommand
from allennlp.common.checks import check_for_gpu, ConfigurationError
from allennlp.common.util import lazy_groups_of
from allennlp.models.archival import load_archive
from allennlp.predictors.predictor import Predictor, JsonDict
from allennlp.data import Instance

from kglm.predictors import CompleteTheSentencePredictor
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.metrics import f1_score
y_true = []
y_pred = []
class CompleteTheSentence(Subcommand):
    def add_subparser(self, name: str, parser: argparse._SubParsersAction) -> argparse.ArgumentParser:
        # pylint: disable=protected-access
        description = '''Run complete the sentence experiments.'''
        subparser = parser.add_parser(
                name, description=description, help='Use a trained model to complete sentences.')

        subparser.add_argument('model_archive_file', type=str, help='the archived model to make predictions with')
        #subparser.add_argument('sampler_archive_file', type=str, help='the archived model to make samples with')
        subparser.add_argument('input_file', type=str, help='path to input file')

        subparser.add_argument('--output-file', type=str, help='path to output file')
        subparser.add_argument('--weights-file',
                               type=str,
                               help='a path that overrides which weights file to use')

        batch_size = subparser.add_mutually_exclusive_group(required=False)
        batch_size.add_argument('--batch-size', type=int, default=1, help='The batch size to use for processing')

        subparser.add_argument('--silent', action='store_true', help='do not print output to stdout')

        cuda_device = subparser.add_mutually_exclusive_group(required=False)
        cuda_device.add_argument('--cuda-device', type=int, default=0, help='id of GPU to use (if any)')

        subparser.add_argument('--use-dataset-reader',
                               action='store_true',
                               help='Whether to use the dataset reader of the original model to load Instances')

        subparser.add_argument('-o', '--overrides',
                               type=str,
                               default="",
                               help='a JSON structure used to override the experiment configuration')

        subparser.set_defaults(func=_predict)

        return subparser


def _get_predictor(args: argparse.Namespace) -> Predictor:
    check_for_gpu(args.cuda_device)
    model = load_archive(args.model_archive_file,
                         weights_file=args.weights_file,
                         cuda_device=args.cuda_device,
                         overrides=args.overrides)
    #sampler = load_archive(args.sampler_archive_file,
    #                       weights_file=args.weights_file,
    #                       cuda_device=args.cuda_device,
    #                       overrides=args.overrides)
    mlines = inspect.getsource(CompleteTheSentencePredictor.from_archive)
    return CompleteTheSentencePredictor.from_archive(model, 'complete-the-sentence')
    #return CompleteTheSentencePredictor.from_archive(model, sampler,
    #                                                 'complete-the-sentence')


class _PredictManager:

    def __init__(self,
                 predictor: Predictor,
                 input_file: str,
                 output_file: Optional[str],
                 batch_size: int,
                 print_to_console: bool,
                 has_dataset_reader: bool) -> None:

        self._predictor = predictor
        self._input_file = input_file
        if output_file is not None:
            self._output_file = open(output_file, "w")
        else:
            self._output_file = None
        self._batch_size = batch_size
        self._print_to_console = print_to_console
        if has_dataset_reader:
            self._dataset_reader = predictor._dataset_reader # pylint: disable=protected-access
        else:
            self._dataset_reader = None
        self.score = 0

    def _predict_json(self, batch_data: List[JsonDict]) -> Iterator[str]:
        if len(batch_data) == 1:
            results = [self._predictor.predict_json(batch_data[0])]
        else:
            results = self._predictor.predict_batch_json(batch_data)
        for output in results:
            yield self._predictor.dump_line(output)

    def _predict_instances(self, batch_data: List[Instance]) -> Iterator[str]:
        if len(batch_data) == 1:
            results = [self._predictor.predict_instance(batch_data[0])]
        else:
            results = self._predictor.predict_batch_instance(batch_data)
        for output in results:
            yield self._predictor.dump_line(output)

    def _maybe_print_to_console_and_file(self,
                                         prediction: str,
                                         model_input: str = None) -> None:
        if self._print_to_console:
            if model_input is not None:
                mi = json.loads(model_input)
                expected_entity = mi['expected_tail']
                print("input: ", expected_entity)
#                print("input: ", model_input)
 #               print("expected:", model_input)
            pr = json.loads(prediction)
            predicted_entity = pr['words'][0]
            print("prediction: ", predicted_entity)
#            print("prediction: ", type(prediction))
        with open('pred_output.txt' , 'a') as the_file:
            for i in range(len(mi['prefix'])):
                print(mi['prefix'][i], end =" ", file = the_file)
            print('\n' + "expected: " + expected_entity + '\t' + "predicted: " + predicted_entity, file=the_file)
            y_true.append(expected_entity)
            y_pred.append(predicted_entity)
            if expected_entity == predicted_entity:
                self.score += self.score
                print("score:", self.score, file=the_file) 
        the_file.close()

        if self._output_file is not None:
            self._output_file.write(prediction)

    def _get_json_data(self) -> Iterator[JsonDict]:
        if self._input_file == "-":
            for line in sys.stdin:
                if not line.isspace():
                    yield self._predictor.load_line(line)
        else:
            with open(self._input_file, "r") as file_input:
                for line in file_input:
                    if not line.isspace():
                        yield self._predictor.load_line(line)

    def _get_instance_data(self) -> Iterator[Instance]:
        if self._input_file == "-":
            raise ConfigurationError("stdin is not an option when using a DatasetReader.")
        elif self._dataset_reader is None:
            raise ConfigurationError("To generate instances directly, pass a DatasetReader.")
        else:
            yield from self._dataset_reader.read(self._input_file)

    def run(self) -> None:
        has_reader = self._dataset_reader is not None
        if has_reader:
            for batch in lazy_groups_of(self._get_instance_data(), self._batch_size):
                for model_input_instance, result in zip(batch, self._predict_instances(batch)):
                    self._maybe_print_to_console_and_file(result, str(model_input_instance))
        else:
            for batch_json in lazy_groups_of(self._get_json_data(), self._batch_size):
                for model_input_json, result in zip(batch_json, self._predict_json(batch_json)):
                    self._maybe_print_to_console_and_file(result, json.dumps(model_input_json))
        print("Expected tail, Prediction",y_true, y_pred)
        binarizer = MultiLabelBinarizer()

        f1 = f1_score(y_true, y_pred, average='macro')
        print("F1 Score:",f1) 
        if self._output_file is not None:
            self._output_file.close()

def _predict(args: argparse.Namespace) -> None:
    predictor = _get_predictor(args)

    if args.silent and not args.output_file:
        print("--silent specified without --output-file.")
        print("Exiting early because no output will be created.")
        sys.exit(0)

    manager = _PredictManager(predictor,
                              args.input_file,
                              args.output_file,
                              args.batch_size,
                              not args.silent,
                              args.use_dataset_reader)
    manager.run()


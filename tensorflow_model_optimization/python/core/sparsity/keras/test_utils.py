# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Test utility to generate models for testing."""

import tempfile
import numpy as np

from tensorflow.python import keras
from tensorflow.python.keras import backend as K
from tensorflow.python.keras.saving import saved_model_experimental
from tensorflow_model_optimization.python.core.sparsity.keras import prune
from tensorflow_model_optimization.python.core.sparsity.keras import pruning_wrapper

l = keras.layers


def _build_mnist_layer_list():
  return [
      l.Conv2D(
          32, 5, padding='same', activation='relu', input_shape=(28, 28, 1)),
      l.MaxPooling2D((2, 2), (2, 2), padding='same'),
      l.BatchNormalization(),
      l.Conv2D(64, 5, padding='same', activation='relu'),
      l.MaxPooling2D((2, 2), (2, 2), padding='same'),
      l.Flatten(),
      l.Dense(1024, activation='relu'),
      l.Dropout(0.4),
      l.Dense(10, activation='softmax')
  ]


def _build_mnist_sequential_model():
  return keras.Sequential(_build_mnist_layer_list())


def _build_mnist_functional_model():
  # pylint: disable=missing-docstring
  inp = keras.Input(shape=(28, 28, 1))
  x = l.Conv2D(32, 5, padding='same', activation='relu')(inp)
  x = l.MaxPooling2D((2, 2), (2, 2), padding='same')(x)
  x = l.BatchNormalization()(x)
  x = l.Conv2D(64, 5, padding='same', activation='relu')(x)
  x = l.MaxPooling2D((2, 2), (2, 2), padding='same')(x)
  x = l.Flatten()(x)
  x = l.Dense(1024, activation='relu')(x)
  x = l.Dropout(0.4)(x)
  out = l.Dense(10, activation='softmax')(x)

  return keras.models.Model([inp], [out])


def _build_mnist_layerwise_pruned_model(pruning_params):
  if pruning_params is None:
    raise ValueError('pruning_params should be provided.')

  return keras.Sequential([
      prune.prune_low_magnitude(
          l.Conv2D(32, 5, padding='same', activation='relu'),
          input_shape=(28, 28, 1),
          **pruning_params),
      l.MaxPooling2D((2, 2), (2, 2), padding='same'),
      l.BatchNormalization(),
      prune.prune_low_magnitude(
          l.Conv2D(64, 5, padding='same', activation='relu'), **pruning_params),
      l.MaxPooling2D((2, 2), (2, 2), padding='same'),
      l.Flatten(),
      prune.prune_low_magnitude(
          l.Dense(1024, activation='relu'), **pruning_params),
      l.Dropout(0.4),
      prune.prune_low_magnitude(
          l.Dense(10, activation='softmax'), **pruning_params)
  ])


def build_mnist_model(model_type, pruning_params=None):
  return {
      'sequential': _build_mnist_sequential_model(),
      'functional': _build_mnist_functional_model(),
      'layer_list': _build_mnist_layer_list(),
      'layer_wise': _build_mnist_layerwise_pruned_model(pruning_params),
  }[model_type]


def model_type_keys():
  return ['sequential', 'functional', 'layer_list', 'layer_wise']


def _save_restore_keras_model(model):
  _, keras_file = tempfile.mkstemp('.h5')
  keras.models.save_model(model, keras_file)

  with prune.prune_scope():
    loaded_model = keras.models.load_model(keras_file)

  return loaded_model


def _save_restore_saved_model(model):
  tmpdir = tempfile.mkdtemp()
  saved_model_experimental.export_saved_model(model, tmpdir)

  with prune.prune_scope():
    loaded_model = saved_model_experimental.load_from_saved_model(tmpdir)

  loaded_model.compile(
      loss='categorical_crossentropy', optimizer='sgd', metrics=['accuracy'])
  return loaded_model


def save_restore_fns():
  return [_save_restore_keras_model, _save_restore_saved_model]


# Assertion/Sparsity Verification functions.


def _get_sparsity(weights):
  return 1.0 - np.count_nonzero(weights) / float(weights.size)


def assert_model_sparsity(test_case, sparsity, model):
  for layer in model.layers:
    if isinstance(layer, pruning_wrapper.PruneLowMagnitude):
      for weight in layer.layer.get_prunable_weights():
        test_case.assertAllClose(sparsity, _get_sparsity(K.get_value(weight)))

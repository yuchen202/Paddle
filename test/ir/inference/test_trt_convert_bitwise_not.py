# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
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

import unittest
from functools import partial
from typing import Any, Dict, List

import numpy as np
from program_config import ProgramConfig, TensorConfig
from trt_layer_auto_scan_test import TrtLayerAutoScanTest

import paddle.inference as paddle_infer


class TrtConvertActivationTest(TrtLayerAutoScanTest):
    def is_program_valid(self, program_config: ProgramConfig) -> bool:
        return True

    def sample_program_configs(self):
        self.trt_param.workspace_size = 1073741824

        def generate_input1(dims, batch, attrs: List[Dict[str, Any]]):
            if dims == 0:
                return np.random.random([]).astype(np.bool8)
            elif dims == 1:
                return np.random.random([32]).astype(np.bool8)
            elif dims == 2:
                return np.random.random([3, 32]).astype(np.int8)
            elif dims == 3:
                return np.random.random([3, 32, 32]).astype(np.int32)
            else:
                return np.random.random([batch, 3, 32, 32]).astype(np.int64)

        for dims in [0, 1, 2, 3, 4]:
            for batch in [1, 4]:
                self.dims = dims
                dics = [{}]

                ops_config = [
                    {
                        "op_type": 'bitwise_not',
                        "op_inputs": {"X": ["input_data"]},
                        "op_outputs": {"Out": ["output_data"]},
                        "op_attrs": dics[0],
                    }
                ]
                ops = self.generate_op_config(ops_config)

                program_config = ProgramConfig(
                    ops=ops,
                    weights={},
                    inputs={
                        "input_data": TensorConfig(
                            data_gen=partial(generate_input1, dims, batch, dics)
                        )
                    },
                    outputs=["output_data"],
                )
                program_config.input_type = program_config.inputs[
                    'input_data'
                ].dtype
                yield program_config

    def sample_predictor_configs(
        self, program_config
    ) -> (paddle_infer.Config, List[int], float):
        def generate_dynamic_shape(attrs):
            if self.dims == 0:
                self.dynamic_shape.min_input_shape = {"input_data": []}
                self.dynamic_shape.max_input_shape = {"input_data": []}
                self.dynamic_shape.opt_input_shape = {"input_data": []}
            elif self.dims == 1:
                self.dynamic_shape.min_input_shape = {"input_data": [1]}
                self.dynamic_shape.max_input_shape = {"input_data": [64]}
                self.dynamic_shape.opt_input_shape = {"input_data": [32]}
            elif self.dims == 2:
                self.dynamic_shape.min_input_shape = {"input_data": [1, 16]}
                self.dynamic_shape.max_input_shape = {"input_data": [4, 32]}
                self.dynamic_shape.opt_input_shape = {"input_data": [3, 32]}
            elif self.dims == 3:
                self.dynamic_shape.min_input_shape = {"input_data": [1, 16, 16]}
                self.dynamic_shape.max_input_shape = {"input_data": [4, 32, 32]}
                self.dynamic_shape.opt_input_shape = {"input_data": [3, 32, 32]}
            else:
                self.dynamic_shape.min_input_shape = {
                    "input_data": [1, 3, 16, 16]
                }
                self.dynamic_shape.max_input_shape = {
                    "input_data": [4, 3, 32, 32]
                }
                self.dynamic_shape.opt_input_shape = {
                    "input_data": [1, 3, 32, 32]
                }

        def clear_dynamic_shape():
            self.dynamic_shape.min_input_shape = {}
            self.dynamic_shape.max_input_shape = {}
            self.dynamic_shape.opt_input_shape = {}

        def generate_trt_nodes_num(attrs, dynamic_shape):
            ver = paddle_infer.get_trt_compile_version()
            trt_version = ver[0] * 1000 + ver[1] * 100 + ver[2] * 10
            if not dynamic_shape:
                if self.dims == 1 or self.dims == 0:
                    return 0, 3
            if program_config.input_type in ['int8', 'uint8']:
                return 0, 3
            elif program_config.input_type == 'bool':
                if trt_version <= 8600 and self.dims == 0:
                    return 0, 3
                elif trt_version <= 8400:
                    return 0, 3
                else:
                    return 1, 2
            else:
                return 1, 2

        attrs = [
            program_config.ops[i].attrs for i in range(len(program_config.ops))
        ]

        # for static_shape
        clear_dynamic_shape()
        self.trt_param.precision = paddle_infer.PrecisionType.Float32
        program_config.set_input_type(np.float32)
        yield self.create_inference_config(), generate_trt_nodes_num(
            attrs, False
        ), 1e-5
        self.trt_param.precision = paddle_infer.PrecisionType.Half
        program_config.set_input_type(np.float16)
        yield self.create_inference_config(), generate_trt_nodes_num(
            attrs, False
        ), 1e-5

        # for dynamic_shape
        generate_dynamic_shape(attrs)
        self.trt_param.precision = paddle_infer.PrecisionType.Float32
        program_config.set_input_type(np.float32)
        yield self.create_inference_config(), generate_trt_nodes_num(
            attrs, True
        ), 1e-5
        self.trt_param.precision = paddle_infer.PrecisionType.Half
        program_config.set_input_type(np.float16)
        yield self.create_inference_config(), generate_trt_nodes_num(
            attrs, True
        ), 1e-5

    def test(self):
        self.run_test()


if __name__ == "__main__":
    unittest.main()

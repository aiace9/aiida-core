# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida_core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
import threading

from plum.utils import AttributesFrozendict
from aiida import work
from aiida.backends.testbase import AiidaTestCase
from aiida.common.lang import override
from aiida.orm import load_node
from aiida.orm.data.base import Int
from aiida.orm.data.frozendict import FrozenDict
from aiida.work import utils
from aiida.work import test_utils

class TestProcessNamespace(AiidaTestCase):

    def setUp(self):
        super(TestProcessNamespace, self).setUp()
        self.assertEquals(len(utils.ProcessStack.stack()), 0)

    def tearDown(self):
        super(TestProcessNamespace, self).tearDown()
        self.assertEquals(len(utils.ProcessStack.stack()), 0)

    def test_namespaced_process(self):
        """
        Test that inputs in nested namespaces are properly validated and the link labels
        are properly formatted by connecting the namespaces with underscores
        """
        class NameSpacedProcess(work.Process):

            @classmethod
            def define(cls, spec):
                super(NameSpacedProcess, cls).define(spec)
                spec.input('some.name.space.a', valid_type=Int)

        proc = NameSpacedProcess(inputs={'some': {'name': {'space': {'a': Int(5)}}}})

        # Test that the namespaced inputs are AttributesFrozenDicts
        self.assertIsInstance(proc.inputs, AttributesFrozendict)
        self.assertIsInstance(proc.inputs.some, AttributesFrozendict)
        self.assertIsInstance(proc.inputs.some.name, AttributesFrozendict)
        self.assertIsInstance(proc.inputs.some.name.space, AttributesFrozendict)

        # Test that the input node is in the inputs of the process
        input_node = proc.inputs.some.name.space.a
        self.assertTrue(isinstance(input_node, Int))
        self.assertEquals(input_node.value, 5)

        # Check that the link of the WorkCalculation node has the correct link name
        self.assertTrue('some_name_space_a' in proc.calc.get_inputs_dict())
        self.assertEquals(proc.calc.get_inputs_dict()['some_name_space_a'], 5)


class ProcessStackTest(work.Process):
    @override
    def _run(self):
        pass

    @override
    def on_create(self):
        super(ProcessStackTest, self).on_create()
        self._thread_id = threading.current_thread().ident

    @override
    def on_stop(self):
        # The therad must match the one used in on_create because process
        # stack is using thread local storage to keep track of who called who
        super(ProcessStackTest, self).on_stop()
        assert self._thread_id is threading.current_thread().ident


class TestProcess(AiidaTestCase):
    def setUp(self):
        super(TestProcess, self).setUp()

        self.assertEquals(len(utils.ProcessStack.stack()), 0)

    def tearDown(self):
        super(TestProcess, self).tearDown()

        self.assertEquals(len(utils.ProcessStack.stack()), 0)

    def test_process_stack(self):
        work.launch.run(ProcessStackTest)

    def test_inputs(self):
        with self.assertRaises(TypeError):
            work.launch.run(test_utils.BadOutput)

    def test_input_link_creation(self):
        dummy_inputs = ["1", "2", "3", "4"]

        inputs = {l: Int(l) for l in dummy_inputs}
        inputs['_store_provenance'] = True
        p = test_utils.DummyProcess(inputs)

        for label, value in p._calc.get_inputs_dict().iteritems():
            self.assertTrue(label in inputs)
            self.assertEqual(int(label), int(value.value))
            dummy_inputs.remove(label)

        # Make sure there are no other inputs
        self.assertFalse(dummy_inputs)

    def test_none_input(self):
        # Check that if we pass no input the process runs fine
        work.launch.run(test_utils.DummyProcess)

    def test_seal(self):
        pid = work.launch.run_get_pid(test_utils.DummyProcess).pid
        self.assertTrue(load_node(pk=pid).is_sealed)

    def test_description(self):
        dp = test_utils.DummyProcess(inputs={'_description': "Rockin' process"})
        self.assertEquals(dp.calc.description, "Rockin' process")

        with self.assertRaises(ValueError):
            test_utils.DummyProcess(inputs={'_description': 5})

    def test_label(self):
        dp = test_utils.DummyProcess(inputs={'_label': 'My label'})
        self.assertEquals(dp.calc.label, 'My label')

        with self.assertRaises(ValueError):
            test_utils.DummyProcess(inputs={'_label': 5})

    def test_work_calc_finish(self):
        p = test_utils.DummyProcess()
        self.assertFalse(p.calc.has_finished_ok())
        work.launch.run(p)
        self.assertTrue(p.calc.has_finished_ok())

    def test_calculation_input(self):
        @work.workfunction
        def simple_wf():
            return {'a': Int(6), 'b': Int(7)}

        outputs, pid = work.launch.run_get_pid(simple_wf)
        calc = load_node(pid)

        dp = test_utils.DummyProcess(inputs={'calc': calc})
        work.launch.run(dp)

        input_calc = dp.calc.get_inputs_dict()['calc']
        self.assertTrue(isinstance(input_calc, FrozenDict))
        self.assertEqual(input_calc['a'], outputs['a'])

    def test_save_instance_state(self):
        proc = test_utils.DummyProcess()
        # Save the instance state
        bundle = work.Bundle(proc)

        proc2 = bundle.unbundle()

class TestFunctionProcess(AiidaTestCase):
    def test_fixed_inputs(self):
        def wf(a, b, c):
            return {'a': a, 'b': b, 'c': c}

        inputs = {'a': Int(4), 'b': Int(5), 'c': Int(6)}
        function_process_class = work.FunctionProcess.build(wf)
        self.assertEqual(work.launch.run(function_process_class, **inputs), inputs)

    def test_kwargs(self):
        def wf_with_kwargs(**kwargs):
            return kwargs

        def wf_without_kwargs():
            return Int(4)

        def wf_fixed_args(a):
            return {'a': a}

        a = Int(4)
        inputs = {'a': a}

        function_process_class = work.FunctionProcess.build(wf_with_kwargs)
        outs = work.launch.run(function_process_class, **inputs)
        self.assertEqual(outs, inputs)

        function_process_class = work.FunctionProcess.build(wf_without_kwargs)
        with self.assertRaises(ValueError):
            work.launch.run(function_process_class, **inputs)

        function_process_class = work.FunctionProcess.build(wf_fixed_args)
        outs = work.launch.run(function_process_class, **inputs)
        self.assertEqual(outs, inputs)

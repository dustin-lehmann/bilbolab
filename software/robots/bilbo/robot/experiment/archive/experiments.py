# import dataclasses
# import numpy as np
#
# # === CUSTOM PACKAGES ==================================================================================================
# from core.utils.control_lib.lib_control.il.ilc import BILBO_BUMPED_REFERENCE_TRAJECTORY, BILBO_REFERENCE_LONGER
# from core.utils.control_lib.lib_control.il.q_filter import design_zero_phase_fir, build_Qf_zero_padded
# from core.utils.control_lib.lib_control.lifted_systems import vec2liftedMatrix, liftedMatrix2Vec
# from core.utils.data import generate_time_vector, generate_random_input, generate_time_vector_by_length
# from core.utils.events import event_definition, Event, OR, wait_for_events, EventFlag
# from core.utils.logging_utils import Logger
# from robots.bilbo.robot.bilbo import BILBO
# from robots.bilbo.robot.bilbo_control import BILBO_Control
# from robots.bilbo.robot.bilbo_core import BILBO_Core
# from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_CONTROL_DT
# # from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_Experiment, BILBO_ExperimentHandler, \
# #     BILBO_Experiment_Events, BILBO_Experiment_Status
# from robots.bilbo.robot.experiment.experiment_definitions import BILBO_OutputTrajectory, BILBO_InputTrajectory
# from robots.bilbo.robot.experiment.experiment_helpers import generate_trajectory_inputs
#
#
# # from robots.bilbo.robot.experiment.definitions import BILBO_OutputTrajectory, BILBO_InputTrajectory
# # from robots.bilbo.robot.experiment.helpers import trajectoryInputToVector, generateTrajectoryInputsFromVector
#
#
# # ======================================================================================================================
# @event_definition
# class DILC_Experiment_Events:
#     started: Event
#     finished: Event
#     aborted: Event
#     status_changed: Event = Event(flags=EventFlag('status', BILBO_Experiment_Status))
#     trajectory_finished: Event
#     trajectory_failed: Event
#     experiment_started: Event
#     update: Event
#
#
# @dataclasses.dataclass
# class DILC_TrajectoryData:
#     trial: int
#
#
# @dataclasses.dataclass
# class DILC_TrialData:
#     index: int
#     input: np.ndarray
#     output: np.ndarray
#     model: np.ndarray
#     error_norm_iml: float
#     error_norm_ilc: float
#
#
# # ======================================================================================================================
# class DILC_Experiment(BILBO_Experiment):
#     FILE_ENDING = '.dilc'
#
#     robot: BILBO
#     reference_trajectory: BILBO_OutputTrajectory
#     reference_trajectory_vec: np.ndarray
#
#     u0: np.ndarray  # Initial guess for the input
#     m0: np.ndarray  # Initial guess for the model
#
#     m: np.ndarray  # Current estimation of the model
#     u: np.ndarray  # Current estimation of the input
#
#     y: np.ndarray
#
#     inputs: list[np.ndarray]
#     outputs: list[np.ndarray]
#
#     trial_index: int
#     num_trials: int = 10
#
#     error_norms_iml: list[float]
#     error_norms_ilc: list[float]
#
#     events: DILC_Experiment_Events
#
#     _N: int
#
#     # q_fc: float = 0.12  # cutoff in cycles/sample (0<fc<0.5)
#     q_fc: float = 0.05  # cutoff in cycles/sample (0<fc<0.5)
#     q_len: int = 41  # odd number of taps
#     q_window: str = "hann"  # "hann" | "hamming" | "blackman"
#     Q_u: np.ndarray  # NxN Toeplitz zero-phase smoothing matrix for u-updates
#
#     q_fc_iml: float = 0.4
#     Q_u_iml: np.ndarray
#
#     # === INIT =========================================================================================================
#     def __init__(self, core: BILBO_Core,
#                  experiment_handler: BILBO_ExperimentHandler,
#                  control: BILBO_Control,
#                  reference_trajectory: BILBO_OutputTrajectory = None):
#
#         super().__init__(core, experiment_handler, control)
#
#         if reference_trajectory is None:
#             self.reference_trajectory = self._generateDefaultReferenceTrajectory()
#             self.reference_trajectory_vec = 1.0 * np.asarray(self.reference_trajectory.output)
#             self.reference_trajectory_vec = self.reference_trajectory_vec
#             self._N = len(self.reference_trajectory_vec)
#
#         # Generate random initial values for u and m
#         self.u0 = generate_random_input(t_vector=self.reference_trajectory.time_vector, f_cutoff=1.5, sigma_I=0.6)
#
#         # self.u0 = np.asarray([-4.05740501e-02, -8.51770989e-02, -1.00180451e-01, -6.01937565e-02,
#         #                       2.11565246e-02, 9.52064689e-02, 1.14278297e-01, 6.78419700e-02,
#         #                       -1.47122295e-02, -9.50460612e-02, -1.57418199e-01, -2.09822508e-01,
#         #                       -2.58630356e-01, -2.89091150e-01, -2.75435263e-01, -2.10356150e-01,
#         #                       -1.22742774e-01, -6.49368299e-02, -7.94909460e-02, -1.70958450e-01,
#         #                       -3.01219149e-01, -4.09632992e-01, -4.45709874e-01, -3.96095069e-01,
#         #                       -2.90195075e-01, -1.81205471e-01, -1.16638762e-01, -1.19380943e-01,
#         #                       -1.87783782e-01, -3.04224485e-01, -4.38475204e-01, -5.47859236e-01,
#         #                       -5.88283501e-01, -5.40053550e-01, -4.30124910e-01, -3.25710647e-01,
#         #                       -2.94932178e-01, -3.60361199e-01, -4.81513581e-01, -5.81856654e-01,
#         #                       -6.01448160e-01, -5.36585157e-01, -4.38332650e-01, -3.73441948e-01,
#         #                       -3.78233398e-01, -4.38201291e-01, -5.04391417e-01, -5.31030303e-01,
#         #                       -5.06656440e-01, -4.58625997e-01, -4.30407123e-01, -4.49222433e-01,
#         #                       -5.07368305e-01, -5.70200199e-01, -6.03842140e-01, -6.00491997e-01,
#         #                       -5.81375472e-01, -5.76085240e-01, -5.96867872e-01, -6.30275928e-01,
#         #                       -6.52915573e-01, -6.56106426e-01, -6.55456747e-01, -6.74508741e-01,
#         #                       -7.16416653e-01, -7.51734120e-01, -7.38779338e-01, -6.63277065e-01,
#         #                       -5.62470908e-01, -5.07579324e-01, -5.52893401e-01, -6.90294064e-01,
#         #                       -8.46757112e-01, -9.29506005e-01, -8.86883521e-01, -7.42003446e-01,
#         #                       -5.77436367e-01, -4.83472332e-01, -5.04472542e-01, -6.15140928e-01,
#         #                       -7.37966545e-01, -7.89767421e-01, -7.30867339e-01, -5.88982299e-01,
#         #                       -4.42068010e-01, -3.67809002e-01, -3.91541537e-01, -4.70222178e-01,
#         #                       -5.26321292e-01, -5.06562411e-01, -4.18247535e-01, -3.14124296e-01,
#         #                       -2.42741764e-01, -2.12190354e-01, -1.99009353e-01, -1.86477806e-01,
#         #                       -1.87726868e-01, -2.29291020e-01, -3.15179000e-01, -4.10889523e-01,
#         #                       -4.63617653e-01, -4.39226452e-01, -3.45340396e-01, -2.26684668e-01,
#         #                       -1.39584584e-01, -1.21121860e-01, -1.68309921e-01, -2.39731140e-01,
#         #                       -2.82232708e-01, -2.67429616e-01, -2.11222555e-01, -1.60169213e-01,
#         #                       -1.55475115e-01, -2.03187226e-01, -2.71679390e-01, -3.14381058e-01,
#         #                       -2.99448797e-01, -2.28442534e-01, -1.35737265e-01, -6.96712730e-02,
#         #                       -6.40908485e-02, -1.15516784e-01, -1.81923945e-01, -2.08079770e-01,
#         #                       -1.63361584e-01, -6.52811258e-02, 3.12435527e-02, 7.39287213e-02,
#         #                       5.23825428e-02, 3.55677824e-03, -2.20861917e-02, -3.45453104e-03,
#         #                       3.82438364e-02, 6.59980504e-02, 6.36515289e-02, 4.56529006e-02,
#         #                       3.34381224e-02, 2.76664589e-02, 8.75771697e-03, -3.39596012e-02,
#         #                       -7.71534424e-02, -7.36140167e-02, 6.69674402e-03, 1.42298292e-01,
#         #                       2.67082728e-01, 3.15635606e-01, 2.69075064e-01, 1.64094210e-01,
#         #                       6.18307010e-02, 6.62346791e-03, 7.55081516e-03, 4.96520229e-02,
#         #                       1.15237896e-01, 1.93215122e-01, 2.72856023e-01, 3.35749625e-01,
#         #                       3.58614676e-01, 3.25936977e-01, 2.41359517e-01, 1.28988603e-01,
#         #                       2.36537449e-02, -4.58595483e-02, -7.40121787e-02, -8.68108450e-02,
#         #                       -1.31784121e-01, -2.49867569e-01, -4.44873354e-01, -6.72861139e-01,
#         #                       -8.61444850e-01, -9.46599643e-01, -9.01767746e-01, -7.42055633e-01,
#         #                       -5.06563826e-01, -2.36516391e-01, 3.45165953e-02, 2.76101852e-01,
#         #                       4.54188376e-01, 5.36290562e-01, 5.09724046e-01, 3.96665369e-01,
#         #                       2.47073466e-01, 1.09674608e-01, 4.93950992e-03, -7.49563401e-02,
#         #                       -1.40778897e-01, -1.83777844e-01, -1.80803723e-01, -1.20891843e-01,
#         #                       -2.38823752e-02, 6.89233715e-02, 1.22296347e-01, 1.26357671e-01,
#         #                       9.30945715e-02, 3.95096392e-02, -2.35328216e-02, -8.83396374e-02,
#         #                       -1.41606152e-01, -1.63646845e-01, -1.40658714e-01, -8.01066498e-02,
#         #                       -1.25399966e-02, 2.67200816e-02, 2.26217062e-02, -1.11873425e-02,
#         #                       -4.91596913e-02, -7.82228858e-02, -1.03648034e-01, -1.32014411e-01,
#         #                       -1.54173752e-01, -1.50730582e-01, -1.14203475e-01, -6.09358334e-02,
#         #                       -1.80203591e-02, 2.73161155e-05])
#
#         self.m0 = generate_random_input(t_vector=self.reference_trajectory.time_vector, f_cutoff=2, sigma_I=0.01)
#
#         # self.m0 = np.asarray([-0.06844697, -0.06133198, -0.00421354, -0.00783946, -0.01921186,
#         #                       -0.03171047, -0.02823364, -0.03311522, -0.04994741, -0.06793569,
#         #                       -0.06662194, -0.0645221, -0.08172677, -0.07230157, -0.07628683,
#         #                       -0.08412534, -0.09660255, -0.06798193, -0.07287573, -0.09550347,
#         #                       -0.07338613, -0.08128396, -0.08167566, -0.063226, -0.05382776,
#         #                       -0.07473619, -0.06338279, -0.04569666, -0.04835554, -0.05519904,
#         #                       -0.04680395, -0.04095645, -0.0629481, -0.02931315, -0.02720207,
#         #                       -0.06209025, -0.03425164, -0.03880779, -0.04393285, -0.04255587,
#         #                       -0.01047659, -0.03514407, -0.03906582, -0.02118262, -0.00250958,
#         #                       -0.01286052, 0.01277022, 0.02074472, -0.02131889, 0.02902772,
#         #                       0.04318309, 0.03157898, 0.05193068, 0.07792574, 0.0916711,
#         #                       0.10125535, 0.11046063, 0.09675491, 0.1074129, 0.1344964,
#         #                       0.14710603, 0.14190557, 0.14118867, 0.14883411, 0.1385682,
#         #                       0.14522745, 0.1366254, 0.12047774, 0.12799755, 0.13364239,
#         #                       0.11884862, 0.09086391, 0.0844365, 0.09012092, 0.07461153,
#         #                       0.06293098, 0.06057469, 0.03028652, 0.03481326, 0.02886604,
#         #                       0.01296223, 0.0195904, 0.01695372, 0.01199298, 0.00226014,
#         #                       -0.00337417, 0.00303691, -0.00305028, -0.02485431, -0.03197195,
#         #                       -0.05163101, -0.04048904, -0.0391673, -0.05289748, -0.04761817,
#         #                       -0.0334281, -0.02408777, -0.03340783, -0.03554072, -0.02630531,
#         #                       -0.0270672, -0.02155042, -0.00928574, 0.00279694, 0.00594078,
#         #                       -0.00696889, 0.00771484, 0.02073746, 0.02956972, 0.00499095,
#         #                       0.01135218, 0.02359572, 0.01360373, 0.00362505, 0.00892573,
#         #                       0.00773568, -0.00253305, 0.00211021, 0.00254718, -0.01614072,
#         #                       -0.02434854, -0.00929701, -0.01738595, -0.03820429, -0.00642805,
#         #                       -0.02727518, -0.02263444, -0.01076897, -0.00278678, -0.01399274,
#         #                       -0.02752018, -0.03749078, -0.02045424, -0.0279218, -0.01826896,
#         #                       -0.02029776, -0.02711239, -0.01876447, 0.00171384, 0.00454513,
#         #                       -0.01306839, 0.00255386, 0.01542455, 0.01454573, 0.01837554,
#         #                       0.00972294, 0.00868395, 0.01152952, 0.02453427, 0.02062412,
#         #                       0.01998317, 0.03555832, 0.04267413, 0.04062069, 0.03715273,
#         #                       0.02340186, 0.02139428, 0.03837721, 0.04085347, 0.02793336,
#         #                       0.02767627, 0.03058087, 0.03260688, 0.03747141, 0.04291113,
#         #                       0.04857149, 0.05165587, 0.04782142, 0.05520525, 0.02262556,
#         #                       0.02443836, 0.03394731, 0.02170053, 0.01108972, 0.02020132,
#         #                       0.00802443, -0.00917834, 0.01519506, 0.00816445, -0.02248726,
#         #                       -0.01822531, 0.0054785, -0.02486159, -0.03758561, -0.0323968,
#         #                       -0.03685464, -0.03473671, -0.02081459, -0.00572201, -0.04761958,
#         #                       -0.0432071, -0.02697418, -0.05307145, -0.05115408, -0.05321538,
#         #                       -0.05623163, -0.04975967, -0.03544016, -0.030088, -0.03338848,
#         #                       -0.03337565, -0.01991501, -0.01556706, -0.0190356, -0.01353768,
#         #                       -0.00109416, -0.00285868, -0.00859185, -0.00274941, -0.01870275,
#         #                       -0.0097374, 0.00681705, -0.00231636, -0.03560196])
#
#         self.error_norms_ilc = []
#         self.error_norms_iml = []
#
#         self.logger = Logger("DILC Experiment", "DEBUG")
#         self.trial_index = 1
#
#         self.events = DILC_Experiment_Events()
#         self.status = BILBO_Experiment_Status.WAITING_FOR_USER
#
#         self._build_input_Q_filter()
#
#         self.u = self.u0
#         self.m = self.m0
#
#         self.outputs = []
#         self.inputs = []
#
#     # === METHODS ======================================================================================================
#     def task(self):
#
#         # Wait for the user to start the experiment
#         self.core.interface_events.start.wait()
#         self.events.experiment_started.set()
#         while not self._exit:
#             self.runTrial()
#
#     def start(self):
#         self.core.speakOnHost(f"Start DILC experiment with {self.num_trials} trials.")
#         super().start()
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def runTrial(self) -> bool:
#         if self.trial_index > self.num_trials:
#             self.finish()
#             return True
#
#         # 1. Generate Input Trajectory from current u
#         input_trajectory = BILBO_InputTrajectory(
#             name=f'DILC Input Trajectory {self.trial_index}',
#             id=self.trial_index,
#             inputs=generate_trajectory_inputs(self.u),
#             dt=BILBO_CONTROL_DT
#             # time_vector=self.reference_trajectory.time_vector,
#             # length=len(self.reference_trajectory.time_vector),
#             # name=f'DILC Input Trajectory {self.trial_index}',
#             # id=self.trial_index,
#             # control_mode=BILBO_Control_Mode.BALANCING,
#             # inputs=generateTrajectoryInputsFromVector(self.u)
#         )
#
#         self.logger.info(f"DILC trial {self.trial_index}/{self.num_trials}. Waiting for user ...")
#         self.core.speakOnHost(f"DILC trial {self.trial_index}")
#
#         self.status = BILBO_Experiment_Status.WAITING_FOR_USER
#
#         data, trace = wait_for_events(
#             events=OR(self.core.interface_events.resume, self.core.interface_events.stop),
#             timeout=None,
#             stale_event_time=None,
#         )
#
#         if trace.caused_by(self.core.interface_events.stop):
#             self.logger.info("Experiment stopped by user. Not implemented yet")
#             return False
#
#         if trace.caused_by(self.core.interface_events.resume):
#             self.logger.info(f"Resume with trajectory {self.trial_index}...")
#
#         # Check the current control mode
#         if self.control.mode != BILBO_Control_Mode.BALANCING:
#             self.logger.warning("Control mode is not balancing. Retrying...")
#             return False
#
#         # Start the trajectory
#         self.core.playSound('notification')
#         self.status = BILBO_Experiment_Status.RUNNING_TRAJECTORY
#         self.core.speakOnHost(f"Trajectory {self.trial_index}...")
#
#         data = self.experiment_handler.run_trajectory(input_trajectory)
#
#         if data is None:
#             self.logger.warning("Trajectory failed")
#             self.events.trajectory_failed.set()
#             return False
#
#         # 3. Extract the output trajectory
#         theta_trajectory = [state.theta for state in data.state_trajectory.states]
#
#         self.core.playSound('notification_double')
#         self.logger.info(f"Trajectory {self.trial_index} finished.")
#         self.core.speakOnHost(f"Trajectory {self.trial_index} finished.")
#
#         self.events.trajectory_finished.set(data={
#             'index': self.trial_index,
#             'data': theta_trajectory,
#             'error_norm': np.linalg.norm(self.reference_trajectory_vec - theta_trajectory)
#         })
#
#         # Now we emit the data and ask the user to resume or revert
#         self.status = BILBO_Experiment_Status.WAITING_FOR_USER
#         self.logger.info(f"Accept the trial or revert it?")
#
#         data, trace = wait_for_events(
#             events=OR(self.core.interface_events.resume, self.core.interface_events.revert),
#             timeout=None,
#             stale_event_time=None,
#         )
#
#         if trace.caused_by(self.core.interface_events.revert):
#             self.logger.info(f"Reverting trial {self.trial_index}")
#             self.core.speakOnHost(f"Reverting trial {self.trial_index}")
#             return False
#
#         self.logger.info(f"Saving trial {self.trial_index}")
#         self.core.speakOnHost(f"Saving trial {self.trial_index}")
#
#         self.y = np.asarray(theta_trajectory)
#
#         self.outputs.append(self.y)
#         self.inputs.append(self.u)
#
#         # Do the Update
#         error_iml = self.y - vec2liftedMatrix(self.m) @ self.u
#         # self.m = self.Q_u_iml @ (self.m + self._getImlLearningMatrix(self.u) @ error_iml)
#         self.m = (self.m + self._getImlLearningMatrix(self.u) @ error_iml)
#
#         error_ilc = self.reference_trajectory_vec - self.y
#
#         self.error_norms_iml.append(np.linalg.norm(error_iml))  # type: ignore
#         self.error_norms_ilc.append(np.linalg.norm(error_ilc))  # type: ignore
#
#         self.events.update.set(data={
#             'index': self.trial_index,
#             'output': self.y,
#             'input': self.u,
#             'error_norm_iml': self.error_norms_iml[-1],
#             'error_norm_ilc': self.error_norms_ilc[-1],
#         })
#
#         self.u = self.Q_u @ (self.u + self._getIlcLearningMatrix(self.m) @ error_ilc)
#         # self.u =  (self.u + self._getIlcLearningMatrix(self.m) @ error_ilc)
#
#         print(repr(self.u))
#         print(repr(self.m))
#
#         self.trial_index += 1
#         return True
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def finish(self):
#         self.logger.important("Experiment finished")
#         self.core.speakOnHost("Experiment finished")
#         self.status = BILBO_Experiment_Status.FINISHED
#         self.stop()
#
#     # === PRIVATE METHODS ==============================================================================================
#     @staticmethod
#     def _generateDefaultReferenceTrajectory():
#         reference_trajectory = BILBO_BUMPED_REFERENCE_TRAJECTORY
#         N = len(reference_trajectory)
#         time_vector = generate_time_vector_by_length(num_samples=N, dt=0.01)
#
#         output_trajectory = BILBO_OutputTrajectory(
#             time_vector=time_vector,
#             output_name='theta',
#             output=reference_trajectory,
#         )
#         return output_trajectory
#
#         time_vector = generate_time_vector(start=0, end=5, dt=0.01)
#         # output_data = np.deg2rad(30) * np.sin(2 * np.pi * time_vector)
#         output_data = np.asarray([0., 0.02612413, 0.05453196, 0.08550183, 0.12034694,
#                                   0.15880929, 0.20140491, 0.24723537, 0.29582374, 0.34625407,
#                                   0.39746831, 0.44860192, 0.49878089, 0.54738697, 0.59388309,
#                                   0.63785555, 0.67897268, 0.71696269, 0.75161612, 0.78276638,
#                                   0.8102765, 0.83403149, 0.8539345, 0.86991927, 0.8819612,
#                                   0.89008431, 0.89435644, 0.89487201, 0.89172829, 0.88499861,
#                                   0.87470927, 0.86082927, 0.84328315, 0.82198847, 0.79690237,
#                                   0.76805441, 0.73555332, 0.69957203, 0.66032285, 0.61803155,
#                                   0.57291484, 0.52516478, 0.47494217, 0.42238019, 0.36759785,
#                                   0.31072121, 0.25190789, 0.19136803, 0.12937476, 0.06626022,
#                                   0.00239885, -0.06181615, -0.12599445, -0.18976195, -0.25276328,
#                                   -0.3146564, -0.37510482, -0.43377391, -0.4903348, -0.5444747,
#                                   -0.59590833, -0.64438351, -0.68967705, -0.73158328, -0.76990331,
#                                   -0.80444436, -0.83503414, -0.86154703, -0.88393165, -0.90222665,
#                                   -0.9165552, -0.92709736, -0.93404929, -0.9375842, -0.93782922,
#                                   -0.93486517, -0.92874631, -0.91952884, -0.90729437, -0.89215822,
#                                   -0.87425967, -0.85373909, -0.83071119, -0.80524387, -0.77734882,
#                                   -0.74698567, -0.71407816, -0.67853864, -0.6402963, -0.59932346,
#                                   -0.55565342, -0.50938412, -0.46066452, -0.40966588, -0.35654656,
#                                   -0.30142297, -0.2443603, -0.1853907, -0.12455733, -0.06197127,
#                                   0.00213799, 0.06739684, 0.13329649, 0.1992339, 0.2645715,
#                                   0.3286972, 0.39106861, 0.45123394, 0.50883155, 0.56357662,
#                                   0.61524319, 0.66364625, 0.70862531, 0.75003088, 0.7877176,
#                                   0.82154827, 0.85140992, 0.87723603, 0.89902435, 0.91683964,
#                                   0.93079704, 0.94103013, 0.9476545, 0.95074, 0.95030325,
#                                   0.94632513, 0.93878774, 0.92771532, 0.91320246, 0.89542013,
#                                   0.8746007, 0.85101024, 0.82491729, 0.79656504, 0.76615017,
#                                   0.7338086, 0.69960671, 0.66353854, 0.62553319, 0.58547744,
#                                   0.54325309, 0.49877863, 0.45203902, 0.40309276, 0.35205858,
#                                   0.29909347, 0.24437392, 0.18808713, 0.13043188, 0.07162466,
#                                   0.01190477, -0.04846555, -0.10920641, -0.17002783, -0.230635,
#                                   -0.29072799, -0.34999481, -0.40810013, -0.46467536, -0.5193169,
#                                   -0.5715985, -0.62109842, -0.66743546, -0.71030224, -0.74948353,
#                                   -0.78485258, -0.81634762, -0.84393957, -0.86760513, -0.88731598,
#                                   -0.90304598, -0.91478967, -0.92258119, -0.92650492, -0.92669493,
#                                   -0.92332632, -0.91660336, -0.90674735, -0.89398392, -0.87852758,
#                                   -0.86056352, -0.84023045, -0.81761093, -0.7927342, -0.76559153,
#                                   -0.73615728, -0.70440586, -0.67031696, -0.63386846, -0.59502414,
#                                   -0.55372697, -0.5099056, -0.46349437, -0.41445998, -0.36282499,
#                                   -0.30868075, -0.25218886, -0.1935745, -0.13311721, -0.07114143,
#                                   -0.00800514, 0.05591729, 0.12025934, 0.18468837, 0.24892177,
#                                   0.31272149, 0.37586284, 0.43808715, 0.49905793, 0.55834118,
#                                   0.61542129, 0.66974909, 0.72080631, 0.76816537, 0.81152688,
#                                   0.85072695, 0.88571707, 0.91652697, 0.94322304, 0.96587267,
#                                   0.98452018, 0.9991755, 1.00981384, 1.01638326, 1.01881731,
#                                   1.01704999, 1.01103097, 1.00073861, 0.98618908, 0.96744054,
#                                   0.94459266, 0.91778296, 0.88718126, 0.85298353, 0.81540513,
#                                   0.77467338, 0.73101986, 0.68467433, 0.63586296, 0.58481325,
#                                   0.53176572, 0.47698821, 0.4207859, 0.36350044, 0.30549528,
#                                   0.24712971, 0.18872773, 0.13054918, 0.0727698, 0.01547556,
#                                   -0.04132562, -0.09767499, -0.15362224, -0.20918189, -0.26429836,
#                                   -0.31882909, -0.37255089, -0.42518712, -0.47644668, -0.52606204,
#                                   -0.57381467, -0.61954198, -0.66312752, -0.70448148, -0.74351963,
#                                   -0.78014632, -0.81424418, -0.84567031, -0.87425788, -0.89982163,
#                                   -0.92216625, -0.94109692, -0.95643083, -0.96800828, -0.97570094,
#                                   -0.97941565, -0.97909353, -0.97470568, -0.96624799, -0.95373729,
#                                   -0.93720999, -0.91672271, -0.89235297, -0.86419767, -0.83236786,
#                                   -0.79698051, -0.75815008, -0.71598437, -0.67058813, -0.62207587,
#                                   -0.57059124, -0.51632796, -0.4595455, -0.40057379, -0.33980446,
#                                   -0.27766937, -0.21461136, -0.15105377, -0.08737621, -0.02390277,
#                                   0.03909506, 0.10138359, 0.16274836, 0.2229804, 0.28187247,
#                                   0.33922421, 0.39485102, 0.44859088, 0.50030522, 0.54987365,
#                                   0.59718514, 0.64212953, 0.68459316, 0.7244599, 0.76161688,
#                                   0.79596241, 0.82741293, 0.85590664, 0.8814019, 0.90387017,
#                                   0.92328477, 0.93960864, 0.95278653, 0.9627463, 0.96941088,
#                                   0.97271705, 0.97263241, 0.96916174, 0.96233841, 0.95220398,
#                                   0.93878576, 0.92208394, 0.90207525, 0.87873224, 0.85204906,
#                                   0.82206139, 0.78885008, 0.75252555, 0.71319735, 0.67093993,
#                                   0.62576699, 0.57762419, 0.52640383, 0.47197801, 0.41424254,
#                                   0.35316192, 0.28880773, 0.2213857, 0.15124892, 0.07889598,
#                                   0.00495317, -0.06985977, -0.14477823, -0.21904985, -0.29198942,
#                                   -0.36301908, -0.43168556, -0.49765596, -0.56070126, -0.62067547,
#                                   -0.67749121, -0.7310883, -0.7813984, -0.8283175, -0.87169885,
#                                   -0.91136785, -0.94715057, -0.97890724, -1.00656402, -1.03013406,
#                                   -1.04971565, -1.06546281, -1.07753578, -1.08604746, -1.091023,
#                                   -1.09238472, -1.08996766, -1.08356054, -1.07295728, -1.05799833,
#                                   -1.03858548, -1.01466861, -0.98621871, -0.95320554, -0.91559043,
#                                   -0.87333491, -0.82642235, -0.77488815, -0.71885271, -0.65854909,
#                                   -0.59433864, -0.52671135, -0.45627145, -0.38371117, -0.30977612,
#                                   -0.23522505, -0.16078711, -0.08712177, -0.01478881, 0.0557656,
#                                   0.12420545, 0.19029001, 0.25385612, 0.31480545, 0.37309799,
#                                   0.4287476, 0.48181285, 0.53238025, 0.58054351, 0.62638739,
#                                   0.6699828, 0.71139247, 0.75067796, 0.787896, 0.82307823,
#                                   0.85619959, 0.88715052, 0.91573005, 0.94166819, 0.9646719,
#                                   0.98447672, 1.00088313, 1.01376507, 1.02305141, 1.02869359,
#                                   1.0306365, 1.02880451, 1.02310437, 1.0134386, 0.9997199,
#                                   0.98188103, 0.95988069, 0.93370984, 0.90340219, 0.86904782,
#                                   0.83080354, 0.78889253, 0.74358885, 0.69518989, 0.64398585,
#                                   0.59023789, 0.53417405, 0.4760051, 0.41595492, 0.35429351,
#                                   0.29135947, 0.22756161, 0.16335759, 0.09921469, 0.035563,
#                                   -0.02724845, -0.08898502, -0.14954443, -0.20895601, -0.26735827,
#                                   -0.32495413, -0.3819483, -0.43847837, -0.49455718, -0.55004449,
#                                   -0.60465891, -0.65802668, -0.70974825, -0.75945605, -0.80684182,
#                                   -0.85164836, -0.89363666, -0.93254926, -0.96808937, -0.99992491,
#                                   -1.0277131, -1.05113122, -1.06989804, -1.08377814, -1.09257569,
#                                   -1.09613237, -1.09433777, -1.08714878, -1.07460543, -1.05683517,
#                                   -1.03404118, -1.00648143, -0.97444761, -0.93825283, -0.8982305,
#                                   -0.85474282, -0.80817768, -0.75895805, -0.70750926, -0.65426191,
#                                   -0.59961742, -0.54388676, -0.48732089, -0.42993719, -0.37179238,
#                                   -0.31263827, -0.25220465, -0.18994812, -0.12631868, -0.06159643,
#                                   0.00297119])
#
#         output_trajectory = BILBO_OutputTrajectory(
#             time_vector=time_vector,
#             output_name='theta',
#             output=output_data,
#         )
#
#         return output_trajectory
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _getImlLearningMatrix(self, u_j):
#         # u = trajectoryInputToVector(input_trajectory.inputs, single_input=True)
#         U = vec2liftedMatrix(u_j)
#
#         W = np.eye(self._N)
#         S = 1.5 * (U.T @ U + 1e-6 * np.eye(self._N))
#         jitter = 1e-8 * np.eye(self._N)
#         A = U @ W @ U.T + S + jitter
#         gain = np.linalg.solve(A, U @ W)
#         L_m = gain.T
#         return L_m
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _getIlcLearningMatrix(self, m_j: np.ndarray):
#         M = vec2liftedMatrix(m_j)
#         W = np.eye(self._N)
#         S = 1.5 * (M.T @ M + 1e-6 * np.eye(self._N))
#         jitter = 1e-8 * np.eye(self._N)
#         A = M @ W @ M.T + S + jitter
#         gain = np.linalg.solve(A, M @ W)
#         L_ilc = gain.T
#         return L_ilc
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _build_input_Q_filter(self):
#         # Design symmetric zero-phase FIR and convert to Toeplitz (zero-padded) matrix
#         h = design_zero_phase_fir(fc=self.q_fc, L=self.q_len, window=self.q_window)
#         Q = build_Qf_zero_padded(h, self._N)
#         # Numerically enforce symmetry and unit DC gain
#         Q = 0.5 * (Q + Q.T)
#         ones = np.ones(self._N)
#         dc_gain = (ones @ (Q @ ones)) / (ones @ ones)  # average row sum
#         if dc_gain != 0:
#             Q = Q / dc_gain
#         self.Q_u = Q
#
#         h_iml = design_zero_phase_fir(fc=self.q_fc_iml, L=self.q_len, window=self.q_window)
#         Q_iml = build_Qf_zero_padded(h_iml, self._N)
#         Q_iml = 0.5 * (Q_iml + Q_iml.T)
#         dc_gain = (ones @ (Q_iml @ ones)) / (ones @ ones)  # average row sum
#         if dc_gain != 0:
#             Q_iml = Q_iml / dc_gain
#         self.Q_u_iml = Q_iml
#
# # ======================================================================================================================
# # class IML_Experiment(BILBO_Experiment):
# #     FILE_ENDING = '.iml'
# #
# #     trial_index: int  # Trial index
# #     N: int  # Number of samples in P
# #
# #     m: np.ndarray  # Current estimation of the model
# #
# #     input_trajectories: list[BILBO_InputTrajectory]
# #     output_trajectories: list[BILBO_OutputTrajectory]
# #     error_norms: list[float]
# #
# # === INIT =========================================================================================================
# #     def __init__(self, N: int, m0: np.ndarray = None):
# #         super().__init__()
# #         self.N = N
# #         self.trial_index = 0
# #
# #         if m0 is None:
# #             m0 = ...
# #
# #     # === PROPERTIES =================================================================================================
# #     @property
# #     def M(self):
# #         return vec2liftedMatrix(self.m)
# #
# #     @M.setter
# #     def M(self, value):
# #         self.m = liftedMatrix2Vec(value)
# #
# #     # === METHODS ====================================================================================================
# #     def start(self):
# #         ...
# #
# #     # ----------------------------------------------------------------------------------------------------------------
# #     def runTrial(self):
# #         ...
# #
# #     # === PRIVATE METHODS ============================================================================================
# #     def _updateEstimation(self, u_j: BILBO_InputTrajectory, y_j: np.ndarray) -> np.ndarray:
# #         e_j = y_j - self.M @ u_j
# #
# #         Lj = self._getLearningMatrix(u_j)
# #
# #         m_j_1 = self.m + Lj @ e_j
# #
# #         return m_j_1
# #
# #     # ----------------------------------------------------------------------------------------------------------------
# #     def _generateRandomInput(self):
# #         ...
# #
# #     # ----------------------------------------------------------------------------------------------------------------
# #     def _getLearningMatrix(self, input_trajectory: BILBO_InputTrajectory) -> np.ndarray:
# #         """
# #         Compute the NO-IML learning matrix:
# #             L = (U^T Q U + S)^(-1) U^T Q
# #         with Q = I and S = ||U||_2^2 I, where U is the lifted input matrix.
# #
# #         Returns
# #         -------
# #         L : np.ndarray of shape (N, N)
# #         """
# #         # Build lifted input matrix U (shape N x N)
# #         u_vec = trajectoryInputToVector(input_trajectory.inputs)  # shape (N, 1) or (N,)
# #         U = vec2liftedMatrix(u_vec)
# #
# #         # Dimensions (trust self.N if provided, else infer)
# #         N = getattr(self, "N", None) or U.shape[0]
# #
# #         # Q = I_N
# #         Q = np.eye(N)
# #
# #         # S = ||U||_2^2 * I_N (spectral norm squared)
# #         sigma_max = np.linalg.norm(U, 2)
# #         S = (sigma_max ** 2) * np.eye(N)
# #
# #         # Form normal matrix and right-hand side
# #         A = U.T @ (Q @ U) + S
# #         B = U.T @ Q
# #
# #         # Solve A * L = B (more stable than taking the explicit inverse)
# #         L = np.linalg.solve(A, B)
# #         return L
# #
# #
# # # ====================================================================================================================
# # class ILC_Experiment:
# #     FILE_ENDING = '.ilc'
# #
# #     robot: BILBO
# #     reference_trajectory: BILBO_OutputTrajectory
# #     u_0: BILBO_InputTrajectory | None = None
# #
# #     P: Union[np.ndarray, None]  # P-Matrix
# #
# #     s: float  # design parameter
# #     r: float  # design parameter
# #
# #     j: int  # Trial index
# #
# #     # === INIT =======================================================================================================
# #     def __init__(self,
# #                  robot: BILBO,
# #                  reference_trajectory: BILBO_OutputTrajectory,
# #                  u_0: BILBO_InputTrajectory | None = None,
# #                  P: Union[np.ndarray, None] = None):
# #
# #         self.robot = robot
# #         self.reference_trajectory = reference_trajectory
# #         self.u_0 = u_0
# #         self.P = P
# #
# #     # === PROPERTIES =================================================================================================
# #     @property
# #     def P(self):
# #         return self._P
# #
# #     @P.setter
# #     def P(self, value):
# #         # Set default value
# #         if value is None:
# #             self._P = None
# #             return
# #         # Check if the value is valid
# #         if not isinstance(value, np.ndarray):
# #             raise ValueError("P-Matrix must be a numpy array")
# #
# #         if not value.shape == (len(self.reference_trajectory.time_vector), len(self.reference_trajectory.time_vector)):
# #             raise ValueError("P-Matrix must be a square matrix with the same dimensions as the reference trajectory")
# #
# #         self._P = value
# #
# #     # === METHODS ====================================================================================================
# #     def start(self):
# #
# #         if self.P is None:
# #             raise ValueError("P-Matrix is not set")
# #
# #     # ----------------------------------------------------------------------------------------------------------------
# #     def runTrial(self):
# #         ...
# #
# #     # === PRIVATE METHODS ============================================================================================
# #     def _updateInput(self):
# #         ...
# #
# # # ====================================================================================================================
# # class DILC_RLS_Experiment:
# #     FILE_ENDING = '.dilcrls'
# #     ...
# #
# #
# # # ====================================================================================================================
# # class IITL_Experiment:
# #     FILE_ENDING = '.iitl'
# #     ...

from typing import Tuple, Union

from gym import spaces
from gym_PBN.envs.pbcn_env import PBCNEnv
from gym_PBN.envs.pbn_env import PBNEnv
from gym_PBN.types import GYM_STEP_RETURN
from gym_PBN.utils import booleanize
from gym_PBN.utils.gym import DiscreteRange

# Types
PBCN_MACRO_ACTION = Tuple[Tuple[Union[int, bool]], int]


class PBNSampledDataEnv(PBNEnv):
    def __init__(
        self,
        PBN_data=[],
        logic_func_data=None,
        goal_config: dict = None,
        reward_config: dict = None,
        gamma: float = 0.99,
        T: int = None,
    ):
        super().__init__(
            PBN_data=PBN_data,
            logic_func_data=logic_func_data,
            goal_config=goal_config,
            reward_config=reward_config,
        )

        # Params
        self.gamma = gamma

        # Gym
        self.T = T if T is not None else 2 ** self.PBN.N
        self.primitive_action_space = spaces.Discrete(self.PBN.N + 1)
        self.interval_space = DiscreteRange(1, self.T)
        self.action_space = spaces.Tuple(
            (self.primitive_action_space, self.interval_space)
        )
        self.discrete_action_space = spaces.Discrete(
            self.primitive_action_space.n * self.interval_space.n
        )

    def step(self, action: Tuple[int, int]) -> GYM_STEP_RETURN:
        if not self.action_space.contains(action):
            raise Exception(f"Invalid action {action}, not in action space.")

        control_action, interval = action

        total_reward = 0
        for i in range(interval):
            # Take action
            if control_action != 0:  # Action 0 is taking no action.
                self.PBN.flip(control_action - 1)

            # Synchronous step / update in the network
            self.PBN.step()

            # Calculate reward
            # TODO Augment reward function
            observation = self.PBN.state
            reward, done = self._get_reward(observation, control_action)
            total_reward += (self.gamma ** i) * reward

        return observation, total_reward, done, {
            "control_action": control_action,
            "interval": i,
            "observation_idx": self._state_to_idx(observation)
        }


class PBCNSampledDataEnv(PBCNEnv):
    def __init__(
        self,
        PBN_data=[],
        logic_func_data=None,
        goal_config: dict = None,
        reward_config: dict = None,
        gamma: float = 0.99,
        T: int = None,
    ):
        super().__init__(PBN_data, logic_func_data, goal_config, reward_config)

        # Params
        self.gamma = gamma

        # Update Gym
        self.observation_space = spaces.MultiBinary(self.PBN.N)
        self.observation_space.dtype = bool

        self.T = T if T is not None else 2 ** self.PBN.N
        self.primitive_action_space = spaces.MultiBinary(self.PBN.M)
        self.primitive_action_space.dtype = bool
        self.interval_space = DiscreteRange(1, self.T)
        self.action_space = spaces.Tuple(
            (self.primitive_action_space, self.interval_space)
        )
        self.discrete_action_space = spaces.Discrete(
            self.primitive_action_space.n * self.interval_space.n
        )

    def _idx_to_macro_action(self, i: int) -> PBCN_MACRO_ACTION:
        action = booleanize(
            i % (2 ** self.primitive_action_space.n), self.primitive_action_space.n
        ).tolist()
        interval = i // (2 ** self.primitive_action_space.n) + 1
        return action, interval

    def step(self, action: Union[PBCN_MACRO_ACTION, int]) -> GYM_STEP_RETURN:
        if action is None:
            raise Exception(
                "You need to provide a macro action with either `macro_action` or `macro_action_discrete`."
            )

        if type(action) is int:
            if not self.discrete_action_space.contains(action):
                raise Exception(f"Invalid action {action}, not in action space.")

            action = self._idx_to_macro_action(action)

        if not self.action_space.contains(action):
            raise Exception(f"Invalid action {action}, not in action space.")

        control_action, interval = action

        time_step_cost = 1

        total_reward, done_step = 0, None
        for i in range(interval):
            # Take action
            self.PBN.apply_control(control_action)

            # Synchronous step / update in the network
            self.PBN.step()

            # Calculate reward
            observation = self.PBN.state
            reward, done = self._get_reward(observation)
            reward -= time_step_cost

            # Penalize overshooting the attractor
            if done_step is not None:
                reward -= self.successful_reward
                # reward -= 8 * time_step_cost
            elif done:
                done_step = i

            total_reward += reward

        return (
            observation,
            total_reward,
            done,
            {
                "control_action": control_action,
                "interval": interval,
                "observation_idx": self._state_to_idx(observation),
            },
        )

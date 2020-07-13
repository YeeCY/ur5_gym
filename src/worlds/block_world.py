"""

World without any objects

Based on https://github.com/rlworkgroup/gym-sawyer/blob/master/sawyer/ros/worlds/block_world.py

"""

import collections
import os.path as osp

from gazebo_msgs.msg import ModelStates
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion, \
    TransformStamped
import gym
import numpy as np
import rospy

from src.objects import Block
from src.worlds.world import World

# from sawyer.ros.worlds.gazebo import Gazebo
# from sawyer.ros.worlds.world import World
# import sawyer.garage.misc.logger as logger
# try:
#     from sawyer.garage.config import VICON_TOPICS
# except ImportError:
#     raise NotImplementedError(
#         "Please set VICON_TOPICS in sawyer.garage.config_personal.py! "
#         "example 1:"
#         "   VICON_TOPICS = ['<vicon_topic_name>']"
#         "example 2:"
#         "   # if you are not using real robot and vicon system"
#         "   VICON_TOPICS = []")


class BlockWorld(World):
    def __init__(self, moveit_scene, frame_id, simulated=False):
        """
        Users use this to manage world and get world state.
        """
        self._blocks = []
        self._simulated = simulated
        self._block_states_subs = []
        self._moveit_scene = moveit_scene
        self._frame_id = frame_id

    def reset(self):
        if self._simulated:
            Gazebo.load_gazebo_model(
                'table',
                Pose(position=Point(x=0.75, y=0.0, z=0.0)),
                osp.join(World.MODEL_DIR, 'cafe_table/model.sdf'))
            Gazebo.load_gazebo_model(
                'block',
                Pose(position=Point(x=0.5725, y=0.1265, z=0.90)),
                osp.join(World.MODEL_DIR, 'block/model.urdf'))
            block = Block(
                name='block',
                initial_pos=(0.5725, 0.1265, 0.90),
                random_delta_range=0.15,
                resource=osp.join(World.MODEL_DIR, 'block/model.urdf'))
            # Waiting models to be loaded
            rospy.sleep(1)
            self._block_states_subs.append(
                rospy.Subscriber('/gazebo/model_states', ModelStates,
                                 self._gazebo_update_block_states))
            self._blocks.append(block)
        else:
            for vicon_topic in VICON_TOPICS:
                block = Block(
                    name='block',
                    initial_pos=(0.5725, 0.1265, 0.90),
                    random_delta_range=0.15,
                    resource=vicon_topic)
                self._block_states_subs.append(
                    rospy.Subscriber(block.resource, TransformStamped,
                                     self._vicon_update_block_states))
                self._blocks.append(block)

        # Add table to moveit
        pose_stamped = PoseStamped()
        pose_stamped.header.frame_id = self._frame_id
        pose_stamped.pose.position.x = 0.655
        pose_stamped.pose.position.y = 0
        # Leave redundant space
        pose_stamped.pose.position.z = -0.02
        pose_stamped.pose.orientation.x = 0
        pose_stamped.pose.orientation.y = 0
        pose_stamped.pose.orientation.z = 0
        pose_stamped.pose.orientation.w = 1.0
        self._moveit_scene.add_box('table', pose_stamped, (1.0, 0.9, 0.1))

    def _gazebo_update_block_states(self, data):
        model_states = data
        model_names = model_states.name
        for block in self._blocks:
            block_idx = model_names.index(block.name)
            block_pose = model_states.pose[block_idx]
            block.position = block_pose.position
            block.orientation = block_pose.orientation

    def _vicon_update_block_states(self, data):
        translation = data.transform.translation
        rotation = data.transform.rotation
        child_frame_id = data.child_frame_id

        for block in self._blocks:
            if block.resource == child_frame_id:
                block.position = translation
                block.orientation = rotation

    def reset(self):
        if self._simulated:
            self._reset_sim()
        else:
            self._reset_real()

    def _reset_sim(self):
        """
        reset the simulation
        """
        # Randomize start position of blocks
        for block in self._blocks:
            block_random_delta = np.zeros(2)
            while np.linalg.norm(block_random_delta) < 0.1:
                block_random_delta = np.random.uniform(
                    -block.random_delta_range,
                    block.random_delta_range,
                    size=2)
            Gazebo.set_model_pose(
                block.name,
                new_pose=Pose(
                    position=Point(
                        x=block.initial_pos.x + block_random_delta[0],
                        y=block.initial_pos.y + block_random_delta[1],
                        z=block.initial_pos.z)))

    def _reset_real(self):
        """
        reset the real
        """
        # randomize start position of blocks
        for block in self._blocks:
            block_random_delta = np.zeros(2)
            new_pos = block.initial_pos
            while np.linalg.norm(block_random_delta) < 0.1:
                block_random_delta = np.random.uniform(
                    -block.random_delta_range,
                    block.random_delta_range,
                    size=2)
            new_pos.x += block_random_delta[0]
            new_pos.y += block_random_delta[1]
            logger.log('new position for {} is x = {}, y = {}, z = {}'.format(
                block.name, new_pos.x, new_pos.y, new_pos.z))
            ready = False
            while not ready:
                ans = input(
                    'Have you finished setting up {}?[Yes/No]\n'.format(
                        block.name))
                if ans.lower() == 'yes' or ans.lower() == 'y':
                    ready = True

    def terminate(self):
        for sub in self._block_states_subs:
            sub.unregister()

        if self._simulated:
            for block in self._blocks:
                Gazebo.delete_gazebo_model(block.name)
            Gazebo.delete_gazebo_model('table')
        else:
            ready = False
            while not ready:
                ans = input('Are you ready to exit?[Yes/No]\n')
                if ans.lower() == 'yes' or ans.lower() == 'y':
                    ready = True

        self._moveit_scene.remove_world_object('table')

    def get_observation(self):
        blocks_pos = np.array([])
        blocks_ori = np.array([])

        for block in self._blocks:
            pos = np.array(
                [block.position.x, block.position.y, block.position.z])
            ori = np.array([
                block.orientation.x, block.orientation.y, block.orientation.z,
                block.orientation.w
            ])
            blocks_pos = np.concatenate((blocks_pos, pos))
            blocks_ori = np.concatenate((blocks_ori, ori))

        achieved_goal = np.squeeze(blocks_pos)

        obs = np.concatenate((blocks_pos, blocks_ori))

        Observation = collections.namedtuple('Observation',
                                             'obs achieved_goal')

        observation = Observation(obs=obs, achieved_goal=achieved_goal)

        return observation

    @property
    def observation_space(self):
        return gym.spaces.Box(
            -np.inf,
            np.inf,
            shape=self.get_observation().obs.shape,
            dtype=np.float32)

    def add_block(self, block):
        if self._simulated:
            Gazebo.load_gazebo_model(
                block.name, Pose(position=block.initial_pos), block.resource)
            # Waiting model to be loaded
            rospy.sleep(1)
        else:
            self._block_states_subs.append(
                rospy.Subscriber(block.resource, TransformStamped,
                                 self._vicon_update_block_states))
        self._blocks.append(block)
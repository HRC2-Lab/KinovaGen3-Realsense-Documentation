# Kinova Gen3 Robot Runtime README

This README describes the full robot runtime pipeline used in our lab for the Kinova Gen3 arm. The system is built entirely on ROS 2 and integrates the Kinova robot, Intel RealSense cameras, Xbox-controller teleoperation for data collection, rosbag logging, and execution of a trained Pi0 policy.

This system supports two main workflows:

1. Data collection using teleoperation and rosbag recording
2. Running a trained Pi0 model in real time on the robot

All robot communication, sensing, and actuation is handled through ROS 2.

External packages used by this system:

Kinova ROS wrapper
https://github.com/Kinovarobotics/ros2_kortex

Intel RealSense ROS wrapper
https://github.com/realsenseai/realsense-ros

Teleop_Twist_Joy
https://docs.ros.org/en/iron/p/teleop_twist_joy/


## System Overview

The robot loop consists of the following components:

- Kinova Gen3 robot arm
- Two Intel RealSense cameras
- ROS controllers for trajectory and twist control
- Xbox controller teleoperation
- Custom ROS nodes for gripper control and model inference

We use `ros2_kortex` as the ROS wrapper for the Kinova Gen3 arm. This is used to:

- Connect ROS 2 to the robot
- Read joint positions and gripper position from `/joint_states`
- Send joint and gripper commands through the Kinova control stack
- Switch between controllers depending on the workflow

For standard motion execution and model inference, we use the joint trajectory controller.

For data collection, we switch from the trajectory controller to the twist controller so the arm can be driven interactively using joystick teleoperation.

We use the ROS 2 wrapper for Intel RealSense cameras to run both the wrist camera and the external camera.

The robot system relies heavily on the following:

- `/joint_states` for robot state
- RealSense camera topics for wrist and external visual observations
- `teleop_twist_joy` for joystick teleoperation
- rosbag recording for dataset generation
- `inferenceloopRTC.py` for real-time Pi0 inference and execution


## Workspace Assumptions

The examples below assume you are working inside the ROS 2 workspace used by the lab.

Typical reminders:

- Source your ROS 2 environment before running anything
- Source your workspace after building
- Make sure the robot laptop is on the correct ethernet configuration
- Make sure both RealSense cameras are plugged in before launch

Typical shell setup:

  source /opt/ros/humble/setup.bash
  source ~/ros2_ws/install/setup.bash

If your workspace path is different, adjust accordingly.


## 1. Robot Network Setup

Before launching the robot, make sure the laptop ethernet interface is configured correctly.

The Kinova robot default IP is:

- `192.168.1.10`

The laptop ethernet static IP should be set to:

- `192.168.1.11`
- netmask `255.255.255.0`

If you are unsure which ethernet device is the robot cable, unplug the cable and compare the output of:

  ip a

Then reconnect it and identify the interface that reappears.

If needed, open the Network Manager editor:

  sudo nm-connection-editor

For the relevant wired connection:

- Set IPv4 Method to `Manual`
- Set address to `192.168.1.11`
- Set netmask to `255.255.255.0`

After saving, test connectivity:
```
  ping 192.168.1.10
```

## 2. Base Robot Bringup

The first thing you should launch is the Kinova driver.

Example:
```
  ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```
This brings up the Gen3 arm and the Robotiq gripper using `ros2_kortex`.

After launch, verify that the robot is publishing joint states:
```
  ros2 topic echo /joint_states
```
You do not need to leave `ros2 topic echo` running forever. This is just a quick sanity check.

At this point the robot should be connected and ready, and the controllers should be available through the controller manager.


## 3. Base Camera Bringup

The system uses two RealSense cameras. Each camera has its own serial number. For example, here are the serial numbers of the two cameras used in the study:

- D415 serial: `021422060548`
- D435i serial: `947522071402`

First, confirm that both cameras are visible:
```
  rs-enumerate-devices
```
Then launch the dual camera node:
```
  ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402
```
Important:

- Use the underscore prefix exactly as shown in the serial arguments
- The cameras are connected to the laptop, not to the arm

Typical image topics used in this project include:

- `/camera1/camera1/color/image_raw`
- `/camera2/camera2/color/image_raw`
- `/camera1/camera1/color/image_raw/compressed`
- `/camera2/camera2/color/image_raw/compressed`

To visually confirm the streams, you can launch RViz:
```
  rviz2
```
Then add Image displays for topics such as:

- `/camera1/color/image_raw`
- `/camera2/color/image_raw`

Depending on your launch setup and namespaces, you may instead use the `camera1/camera1/...` and `camera2/camera2/...` versions of the topic names. Always verify the exact topic names with:
```
  ros2 topic list
```

## 4. Optional: Home the Robot

If needed, home the robot before collecting data.

Important safety notes:

- This move does not include collision avoidance
- Make sure the path to home is clear
- The example below uses 10 seconds for the move
- If the arm is far from home, increase the time

To home the robot, first switch back to the joint trajectory controller:
```
  ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController "{
  activate_controllers: [joint_trajectory_controller],
  deactivate_controllers: [twist_controller],
  strictness: 1,
  activate_asap: true,
  }"
```
Then send the homing trajectory:
```
  ros2 action send_goal /joint_trajectory_controller/follow_joint_trajectory control_msgs/action/FollowJointTrajectory "{trajectory: {joint_names: [joint_1, joint_2, joint_3, joint_4, joint_5, joint_6, joint_7], points: [{positions: [0.0, -0.3491, -3.1415, -2.5484, 0.0, -0.8726, 1.5708], time_from_start: {sec: 10, nanosec: 0}}]}}"
```
If you plan to continue with teleop data collection afterward, switch back to twist control once homing is complete.


## Data Collection Workflow

Data collection is used to record teleoperated demonstrations for training.

At a high level, the process is:

1. Launch the robot
2. Launch the cameras
3. Optionally home the robot
4. Switch from trajectory control to twist control
5. Launch joystick teleoperation
6. Launch the custom gripper-control node
7. Record the required topics with rosbag


## 5. Switch to Twist Controller for Teleoperation

For data collection, the robot is controlled through twist commands rather than trajectory goals.

Switch controllers with:
```
  ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController "{
  activate_controllers: [twist_controller],
  deactivate_controllers: [joint_trajectory_controller],
  strictness: 1,
  activate_asap: true,
  }"
```
This must be done before running joystick teleoperation.


## 6. Launch teleop_twist_joy

Once the twist controller is active, launch `teleop_twist_joy` so the Xbox controller can drive the robot.

The Xbox controller is connected to the laptop via USB.

We use the custom joystick mapping file:

- `better_xbox.config.yaml`

Configuration files for teleop should be located in `/opt/ros/humble/share/teleop_twist_joy/config`, So the yaml file should be placed in the following location:

- `/opt/ros/humble/share/teleop_twist_joy/config/better_xbox.config.yaml`

Example launch:
```
  ros2 launch teleop_twist_joy teleop-launch.py joy_config:='better_xbox' joy_vel:='/twist_controller/commands'
```
This publishes joystick commands to the twist controller.

Current important mappings from `better_xbox.config.yaml`:

- linear x uses axis 1
- linear y uses axis 0
- linear z uses axis 4
- linear scales:
  - x: `0.05`
  - y: `-0.05`
  - z: `-0.03`
- enable button: `5`

In practice, this means the custom config is tuned for slow, controlled motion suitable for demonstration collection.


## 7. Launch joy_to_kinova.py for Gripper Control

Arm motion is handled through `teleop_twist_joy`, but gripper control is handled separately by the custom script:

- `joy_to_kinova.py`

Run it in another terminal after teleop is active:
```
  python3 ../path/to/joy_to_kinova.py
```
This node:

- subscribes to `/joy`
- opens a ROS action client to `/robotiq_gripper_controller/gripper_cmd`
- uses button `0` as the open button
- uses button `1` as the close button
- changes gripper position in increments of `0.08`
- clamps the gripper range between `0.0` and `0.8`

So the intended workflow is:

- use the joystick to move the arm
- use the gripper buttons to open and close the gripper incrementally

This makes the demonstrations much easier to collect than relying on arm teleop alone.


## 8. Record Demonstrations with rosbag

Once the robot, cameras, teleop node, and gripper-control node are all running, record the session with rosbag.

Use the dual-camera rosbag command:
```
  ros2 bag record \
  /camera1/camera1/color/image_raw/compressed \
  /camera1/camera1/color/camera_info \
  /camera2/camera2/color/image_raw/compressed \
  /camera2/camera2/color/camera_info \
  /joint_states \
  /tf \
  /tf_static
```
This records:

- both compressed RGB streams
- both camera calibration topics
- robot joint state
- transforms

Press Ctrl+C when the demonstration is complete.

Each recording becomes a rosbag that can later be converted into one training episode in the dataset pipeline.

Each ros2 node/command should be run in a different terminal window. For convenience, the user may install the Terminator Terminal Emulator:
https://github.com/gnome-terminator/terminator

A typical full data-collection session therefore looks like this:

Terminal 1:
```
  ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```
Terminal 2:
```
  ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402
```
Terminal 3:
```
  ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController "{
  activate_controllers: [twist_controller],
  deactivate_controllers: [joint_trajectory_controller],
  strictness: 1,
  activate_asap: true,
  }"
```

Terminal 4:
```
  ros2 launch teleop_twist_joy teleop-launch.py joy_config:='better_xbox' joy_vel:='/twist_controller/commands'
```

Terminal 5:
```
  python3 joy_to_kinova.py
```
Terminal 6:
```
  ros2 bag record \
  /camera1/camera1/color/image_raw/compressed \
  /camera1/camera1/color/camera_info \
  /camera2/camera2/color/image_raw/compressed \
  /camera2/camera2/color/camera_info \
  /joint_states \
  /tf \
  /tf_static
```
Then:
- teleoperate the robot with the Xbox controller
- control the gripper with the button inputs
- stop the bag recording when done (Press Ctrl+C)


## Running the Pi0 Model (Inference Loop)

Once a Pi0 model has been trained, it can be executed on the real robot using the runtime inference loop.

The main script used for this is:

- `inferenceloopRTC.py`

Unlike data collection, this workflow does not use the twist controller.

For model execution, the robot should remain on the joint trajectory controller.


## 10. Inference Setup Summary

Before running `inferenceloopRTC.py`, the following must already be active:

- Kinova arm launched and connected through `ros2_kortex`
- RealSense camera nodes launched
- Joint trajectory controller active

Do not switch to the twist controller for inference.


## 11. Example Inference Workflow

Minimal workflow:

Terminal 1:
```
  ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```
Terminal 2:
```
  ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402
```
Terminal 3:
```
  python3 inferenceloopRTC.py --host 128.253.224.8 --port 8000 --compressed --control-hz 20 --prompt "pick up the blue cup and place it in blue bin" --speed-scale 1.3 --gripper-action position --goal-hz 2
```
This example keeps the inference section intentionally light. The important point is that:

- the robot is already connected
- the cameras are already publishing
- the inference loop reads compressed image topics
- the policy server is already running elsewhere
- the robot stays on the trajectory controller

From the script defaults, the inference loop is set up around:

- external image topic: `/camera1/camera1/color/image_raw/compressed`
- wrist image topic: `/camera2/camera2/color/image_raw/compressed`
- trajectory action namespace: `/joint_trajectory_controller/follow_joint_trajectory`
- gripper action namespace: `/robotiq_gripper_controller/gripper_cmd`

So if you keep the standard topic/controller setup, you usually only need to specify the host, port, prompt, and a few control parameters.


## 12. What inferenceloopRTC.py Does

At a high level, the inference loop does the following:

- reads current robot state from `/joint_states`
- reads the two camera streams
- packages the current observation
- sends the observation to the Pi0/OpenPI inference server
- receives predicted action chunks
- converts those predictions into executable commands
- sends trajectory updates to the robot continuously

It is designed for real-time chunked control rather than one-shot command execution.

You do not need to understand every implementation detail to run it. For onboarding purposes, the main takeaway is:

- launch robot
- launch cameras
- keep the trajectory controller active
- run the script with the correct host/port/prompt


For more information about the inferenceloop, refer the following GitHub Repository: "TODO"


## ROS Components Summary

The full robot system consists of the following ROS nodes and packages:

- `ros2_kortex`
  Kinova ROS wrapper used to connect to the Gen3 arm, expose robot state, and command the robot.

- `realsense-ros`
  ROS wrapper for the wrist and external RealSense cameras.

- `teleop_twist_joy`
  Xbox joystick teleoperation for arm motion during data collection.

- `joy_to_kinova.py`
  Custom node used during teleoperation for precise gripper control.

- rosbag
  Used to record trajectories for training data generation.

- `inferenceloopRTC.py`
  Real-time Pi0 inference loop used to run the trained model on the robot.


## Typical Workflow Summary

### Data Collection

1. Configure ethernet and verify robot connectivity
2. Launch Kinova driver
3. Launch RealSense cameras
4. Home robot if needed
5. Switch to twist controller
6. Launch `teleop_twist_joy` with `better_xbox.config.yaml`
7. Launch `joy_to_kinova.py`
8. Record relevant topics with rosbag
9. Teleoperate the demonstration
10. Stop rosbag recording

### Training

Use the separate dataset pipeline README to:

1. Reorder `/joint_states`
2. Convert rosbags to LeRobot format
3. Train the Pi0 model

### Inference

1. Launch Kinova driver
2. Launch RealSense cameras
3. Keep joint trajectory controller active
4. Run `inferenceloopRTC.py`
5. Execute the Pi0 policy on the robot


## Notes for New Lab Members

- Always verify that `/joint_states` is publishing before doing anything else.
- Confirm that both camera topics are active before starting either collection or inference.
- Use twist control only for data collection.
- Use trajectory control for inference.
- Record demonstrations only after all teleop and gripper-control nodes are working correctly.
- Keep the naming and topic conventions consistent across all recordings so the downstream dataset conversion pipeline remains stable.
- When in doubt, check `ros2 topic list`, `ros2 topic echo [TOPIC_NAME]` `ros2 action list`, and `ros2 control list_controllers` to verify the runtime state.
- Be careful when homing. There is no collision avoidance in the example command.
- If the RealSense topics do not match the examples exactly, inspect the live topic list and update commands accordingly.
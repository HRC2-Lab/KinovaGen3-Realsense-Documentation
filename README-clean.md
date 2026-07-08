# Kinova Gen3 Robot Runtime README
(This is a Claude Code rewrite of the original README.md)

This README describes the full robot runtime pipeline used in our lab for the Kinova Gen3 arm. The system is built entirely on ROS 2 and integrates the Kinova robot, Intel RealSense cameras, Xbox-controller teleoperation for data collection, rosbag logging, and execution of a trained Pi0 policy.

This system supports two main workflows:

1. **Data collection** — teleoperation + rosbag recording
2. **Inference** — running a trained Pi0 model in real time on the robot

All robot communication, sensing, and actuation is handled through ROS 2.

External packages used by this system:

- [Kinova ROS wrapper (`ros2_kortex`)](https://github.com/Kinovarobotics/ros2_kortex)
- [Intel RealSense ROS wrapper (`realsense-ros`)](https://github.com/realsenseai/realsense-ros)
- [`teleop_twist_joy`](https://docs.ros.org/en/iron/p/teleop_twist_joy/)

Files in this repository:

- `rs_dual_camera_launch.py` — lab's custom dual-camera RealSense launch file
- `better_xbox.config.yaml` — Xbox controller joystick mapping for teleop
- `joy_to_kinova.py` — custom gripper-control node used during teleop

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [One-Time Machine Setup](#one-time-machine-setup)
4. [Per-Session Startup](#per-session-startup-shared-by-both-workflows)
5. [Workflow A: Data Collection](#workflow-a-data-collection)
6. [Workflow B: Running Inference](#workflow-b-running-inference)
7. [Reference](#reference)
8. [Troubleshooting & Safety Notes](#troubleshooting--safety-notes)
9. [Related Docs](#related-docs)
10. [Notes for New Lab Members](#notes-for-new-lab-members)

---

## Quick Start

Assumes [One-Time Machine Setup](#one-time-machine-setup) is already done. Each block below runs in its own terminal (many lab members use [Terminator](https://github.com/gnome-terminator/terminator) for this).

### Data Collection Session

# Terminal 1 — robot driver
```
ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```

# Terminal 2 — cameras
```
ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402
```

# Terminal 3 — switch to twist control
```
ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController "{
activate_controllers: [twist_controller],
deactivate_controllers: [joint_trajectory_controller],
strictness: 1,
activate_asap: true,
}"
```

# Terminal 4 — joystick teleop (arm motion)
```
ros2 launch teleop_twist_joy teleop-launch.py joy_config:='better_xbox' joy_vel:='/twist_controller/commands'

# Terminal 5 — gripper control
python3 joy_to_kinova.py

# Terminal 6 — record the demonstration
ros2 bag record \
  /camera1/camera1/color/image_raw/compressed \
  /camera1/camera1/color/camera_info \
  /camera2/camera2/color/image_raw/compressed \
  /camera2/camera2/color/camera_info \
  /joint_states \
  /tf \
  /tf_static
```

Teleoperate with the Xbox stick, control the gripper with the mapped buttons, and press `Ctrl+C` in Terminal 6 to stop recording. Each recording becomes one training episode after dataset conversion.

### Inference Session

# Terminal 1 — robot driver
```
ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```

# Terminal 2 — cameras
```
ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402

# Terminal 3 — run the policy (robot stays on the trajectory controller — do NOT switch to twist)
conda activate openpi_ros
cd ../path/to/script (E.g. ~/pi_ws/openpi-LBMfailure/scripts)
python3 inferenceloopRTC.py --host 128.253.224.8 --port 8000 --compressed --control-hz 20 \
  --prompt "pick up the blue cup and place it in blue bin" --speed-scale 1.3 \
  --gripper-action position --goal-hz 2
```

With the standard topic/controller setup, you generally only need to change `--host`, `--port`, `--prompt`, and control parameters — see [What `inferenceloopRTC.py` Does](#what-inferencelooprtcpy-does) for the defaults it assumes.

---

## Architecture Overview

The robot loop consists of:

- Kinova Gen3 robot arm
- Two Intel RealSense cameras (wrist + external)
- ROS controllers for trajectory and twist control
- Xbox controller teleoperation
- Custom ROS nodes for gripper control and model inference

**`ros2_kortex`** is the ROS wrapper for the Kinova Gen3 arm. It:

- Connects ROS 2 to the robot
- Reads joint positions and gripper position from `/joint_states`
- Sends joint and gripper commands through the Kinova control stack
- Switches between controllers depending on the workflow

Two controllers are used, and the workflow determines which is active:

| Controller | Used for |
|---|---|
| Joint trajectory controller | Standard motion execution, Pi0 inference |
| Twist controller | Interactive joystick teleop during data collection |

**`realsense-ros`** runs both the wrist camera and the external camera.

The system relies heavily on:

- `/joint_states` for robot state
- RealSense camera topics for wrist and external visual observations
- `teleop_twist_joy` for joystick teleoperation
- rosbag recording for dataset generation
- `inferenceloopRTC.py` for real-time Pi0 inference and execution

### ROS Components Summary

| Component | Role |
|---|---|
| `ros2_kortex` | Connects to the Gen3 arm, exposes robot state, commands the robot |
| `realsense-ros` | ROS wrapper for the wrist and external RealSense cameras |
| `teleop_twist_joy` | Xbox joystick teleoperation for arm motion during data collection |
| `joy_to_kinova.py` | Custom node for gripper control during teleoperation |
| rosbag | Records trajectories for training data generation |
| `inferenceloopRTC.py` | Real-time Pi0 inference loop that runs the trained model on the robot |

---

## One-Time Machine Setup

Do this once per lab machine. See [Per-Session Startup](#per-session-startup-shared-by-both-workflows) for what you run every time you use the robot.

### Hardware Requirements

- Kinova Gen3 arm
- Robotiq 2F-85 gripper
- Ubuntu 22.04 machine
- ROS 2 Humble installed
- Ethernet connection to the robot
- Two Intel RealSense cameras
- Xbox controller for teleoperation

### Install ROS 2 Packages

```
sudo apt install ros-humble-kortex-bringup
sudo apt install ros-humble-kinova-gen3-7dof-robotiq-2f-85-moveit-config
sudo apt install ros-humble-realsense2-camera
```

### Fix xacro Parameter Mismatch

Depending on the installed package versions, the apt-installed `robotiq_description` may be missing parameters expected by `kortex_description`.

Edit:
```
sudo nano /opt/ros/humble/share/robotiq_description/urdf/robotiq_2f_85_macro.urdf.xacro
```
Find the line containing:
```
com_port:=/dev/ttyUSB0">
```
and change it to:
```
com_port:=/dev/ttyUSB0
isaac_joint_commands:=false
isaac_joint_states:=false">
```
This resolves a parameter mismatch between the Robotiq and Kortex xacro files.

### Configure Robot Ethernet

The Kinova robot's default IP is `192.168.1.10`. Set the laptop's ethernet interface to:

- Address: `192.168.1.11`
- Netmask: `255.255.255.0`

If you're unsure which ethernet device is the robot cable, unplug it and compare the output of `ip a` before and after reconnecting — the interface that reappears is the robot cable.

Open the Network Manager editor if needed:
```
sudo nm-connection-editor
```
For the relevant wired connection: set IPv4 Method to `Manual`, address to `192.168.1.11`, netmask to `255.255.255.0`.

### Set Up the Pi0 Runtime Conda Environment

The Pi0 runtime controller must run in a separate Python 3.10 conda environment compatible with system ROS 2 Humble. **Do not** use a Python 3.11 environment for the ROS-based controller runtime — `rclpy` will not work correctly against the Humble system install.

```
conda create -n openpi_ros python=3.10 -y
conda activate openpi_ros
pip install numpy opencv-python typing_extensions
pip install -e ~/pi_ws/openpi-LBMfailure/packages/openpi-client
```
This requires having cloned the `openpi-LBMfailure` repository. The path above can be changed, but must point to the `openpi-client` package.

### Locate the Lab's Dual-Camera Launch File

The lab uses a custom `rs_dual_camera_launch.py` (in this repo) that disables unnecessary depth and point cloud processing. Find the installed copy and replace it with the lab version:
```
find ~ -name 'rs_dual_camera_launch.py' 2>/dev/null
```

### Install the Xbox Joystick Config

Configuration files for `teleop_twist_joy` live in `/opt/ros/humble/share/teleop_twist_joy/config`. Place the lab's config there:
```
/opt/ros/humble/share/teleop_twist_joy/config/better_xbox.config.yaml
```

### Workspace Sourcing

```
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
```
Adjust the workspace path if yours differs. Always source ROS 2 before running anything, and re-source your workspace after every build.

---

## Per-Session Startup (shared by both workflows)

Run these steps every time before either data collection or inference. Reminders:

- Make sure the robot laptop is on the correct ethernet configuration
- Make sure both RealSense cameras are plugged in before launch

### 1. Verify Network Connectivity

```
ping 192.168.1.10
```
You can also check the Kinova web interface at `http://192.168.1.10`.

### 2. Launch the Robot Driver

```
ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 gripper:=robotiq_2f_85
```
This brings up the Gen3 arm and Robotiq gripper via `ros2_kortex`.

Verify joint states are publishing (a quick sanity check, not something to leave running):
```
ros2 topic echo /joint_states
```
At this point the robot should be connected and ready, and the controllers should be available through the controller manager.

Optionally test the gripper directly through its action server:
```
# Open
ros2 action send_goal /robotiq_gripper_controller/gripper_cmd control_msgs/action/GripperCommand "{command:{position: 0.0, max_effort: 100.0}}"
# Close
ros2 action send_goal /robotiq_gripper_controller/gripper_cmd control_msgs/action/GripperCommand "{command:{position: 0.7, max_effort: 100.0}}"
```

### 3. Launch the Cameras

Each RealSense camera has its own serial number (see [Reference](#reference)). You can test a single camera first with:
```
ros2 launch realsense2_camera rs_launch.py
```

For dual-camera operation, confirm both are visible, then launch:
```
rs-enumerate-devices
ros2 launch realsense2_camera rs_dual_camera_launch.py serial_no1:=_021422060548 serial_no2:=_947522071402
```
**Important:** use the underscore prefix exactly as shown, and note that the cameras are connected to the laptop, not the arm.

Verify throughput (expect ~30 Hz):
```
ros2 topic list | grep compressed
ros2 topic hz /camera1/camera1/color/image_raw/compressed
ros2 topic hz /camera2/camera2/color/image_raw/compressed
```

To visually confirm streams, launch `rviz2` and add Image displays for topics such as:

- `/camera1/color/image_raw`
- `/camera2/color/image_raw`

Depending on your launch setup and namespaces, you may instead use the `camera1/camera1/...` and `camera2/camera2/...` versions of the topic names. Always verify the exact topic names with `ros2 topic list`.

### 4. Optional: Home the Robot

See [Troubleshooting & Safety Notes](#troubleshooting--safety-notes) before doing this — **homing has no collision avoidance**.

Switch to the joint trajectory controller first:
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
If continuing with teleop data collection afterward, switch back to the twist controller once homing completes.

At this point the robot and cameras are up — proceed to whichever workflow you need.

---

## Workflow A: Data Collection

Used to record teleoperated demonstrations for training. Assumes [Per-Session Startup](#per-session-startup-shared-by-both-workflows) is complete.

### 1. Switch to the Twist Controller

Data collection drives the robot with twist commands rather than trajectory goals — this must happen before joystick teleop:
```
ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController "{
activate_controllers: [twist_controller],
deactivate_controllers: [joint_trajectory_controller],
strictness: 1,
activate_asap: true,
}"
```

### 2. Launch `teleop_twist_joy`

The Xbox controller connects to the laptop via USB. Launch with the lab's custom joystick mapping (`better_xbox.config.yaml`):
```
ros2 launch teleop_twist_joy teleop-launch.py joy_config:='better_xbox' joy_vel:='/twist_controller/commands'
```
This is tuned for slow, controlled motion suitable for demonstration collection — see [Joystick Mapping](#joystick-mapping-betterxboxconfigyaml) in Reference for the exact axis/scale values.

### 3. Launch `joy_to_kinova.py` for Gripper Control

Arm motion is handled by `teleop_twist_joy`; gripper control is separate. Run in another terminal once teleop is active:
```
python3 ../path/to/joy_to_kinova.py
```
This node subscribes to `/joy` and opens an action client to `/robotiq_gripper_controller/gripper_cmd` — see [Reference](#reference) for button mappings and increment values. Intended workflow: use the joystick to move the arm, use the gripper buttons to open/close it incrementally.

### 4. Record with rosbag

Once the robot, cameras, teleop node, and gripper-control node are all running:
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
This records both compressed RGB streams, both camera calibration topics, robot joint state, and transforms. Press `Ctrl+C` when the demonstration is complete. Each recording becomes one training episode in the dataset pipeline.

See [Quick Start](#quick-start) for the full multi-terminal sequence.

---

## Workflow B: Running Inference

Runs a trained Pi0 model on the robot in real time. Assumes [Per-Session Startup](#per-session-startup-shared-by-both-workflows) is complete.

Unlike data collection, this workflow does **not** use the twist controller — the robot stays on the joint trajectory controller throughout.

### Setup Checklist

Before running `inferenceloopRTC.py`, confirm:

- Kinova arm launched and connected through `ros2_kortex`
- RealSense camera nodes launched
- Joint trajectory controller active (do not switch to twist control)

### Run the Inference Loop

```
conda activate openpi_ros
cd ../path/to/script (E.g. ~/pi_ws/openpi-LBMfailure/scripts)
python3 inferenceloopRTC.py --host 128.253.224.8 --port 8000 --compressed --control-hz 20 \
  --prompt "pick up the blue cup and place it in blue bin" --speed-scale 1.3 \
  --gripper-action position --goal-hz 2
```
This example keeps the inference section intentionally light. The important point is that: the robot is already connected, the cameras are already publishing, the inference loop reads compressed image topics, the policy server is already running elsewhere, and the robot stays on the trajectory controller.

### What `inferenceloopRTC.py` Does

At a high level, the inference loop:

- Reads current robot state from `/joint_states`
- Reads the two camera streams
- Packages the current observation
- Sends the observation to the Pi0/OpenPI inference server
- Receives predicted action chunks
- Converts those predictions into executable commands
- Sends trajectory updates to the robot continuously

It's designed for real-time chunked control rather than one-shot command execution. From the script defaults, it assumes:

| Purpose | Default |
|---|---|
| External image topic | `/camera1/camera1/color/image_raw/compressed` |
| Wrist image topic | `/camera2/camera2/color/image_raw/compressed` |
| Trajectory action namespace | `/joint_trajectory_controller/follow_joint_trajectory` |
| Gripper action namespace | `/robotiq_gripper_controller/gripper_cmd` |

With the standard topic/controller setup, you usually only need to specify host, port, prompt, and a few control parameters.

For onboarding purposes, the main takeaway is: launch robot → launch cameras → keep the trajectory controller active → run the script with the correct host/port/prompt.

*(For more detail on the inference loop internals, see the external repo — link TBD, see [Related Docs](#related-docs).)*

---

## Reference

### Camera Serial Numbers

| Camera | Serial |
|---|---|
| D415 | `021422060548` |
| D435i | `947522071402` |

### Key Topics

| Topic | Notes |
|---|---|
| `/joint_states` | Robot joint + gripper position |
| `/camera1/camera1/color/image_raw` | Raw image, camera 1 |
| `/camera2/camera2/color/image_raw` | Raw image, camera 2 |
| `/camera1/camera1/color/image_raw/compressed` | Compressed image, camera 1 (used by rosbag + inference) |
| `/camera2/camera2/color/image_raw/compressed` | Compressed image, camera 2 (used by rosbag + inference) |

Namespacing can vary by launch setup — always confirm with `ros2 topic list`.

### Joystick Mapping (`better_xbox.config.yaml`)

| Axis/Button | Function | Value |
|---|---|---|
| Axis 1 | Linear X | scale `0.05` |
| Axis 0 | Linear Y | scale `-0.05` |
| Axis 4 | Linear Z | scale `-0.03` |
| Button 5 | Enable | — |

### Gripper Control (`joy_to_kinova.py`)

| Button | Function |
|---|---|
| 0 | Open |
| 1 | Close |

Increment step: `0.08` per press. Clamped range: `0.0`–`0.8`.

### Gripper Action Server Values (direct action calls)

| Position | Meaning |
|---|---|
| `0.0` | Fully open |
| `0.7` | Fully closed |

---

## Troubleshooting & Safety Notes

- **Homing has no collision avoidance.** Make sure the path to home is clear before sending the homing trajectory. The example command uses 10 seconds — increase the time if the arm starts far from home.
- If RealSense topics don't match the examples exactly, inspect the live topic list (`ros2 topic list`) and update commands accordingly — namespacing can vary by launch configuration.
- Useful runtime-state checks: `ros2 topic list`, `ros2 topic echo <TOPIC_NAME>`, `ros2 action list`, `ros2 control list_controllers`.
- If the robot isn't connecting, re-check the ethernet setup in [One-Time Machine Setup](#one-time-machine-setup) — verify with `ping 192.168.1.10`.

---

## Related Docs

- **Dataset pipeline README** (separate repo/doc) — covers reordering `/joint_states`, converting rosbags to LeRobot format, and training the Pi0 model. *(Link not yet added — update this section once available.)*
- **`inferenceloopRTC.py` internals** — external GitHub repo. *(TODO: link not yet added.)*

---

## Notes for New Lab Members

- Always verify that `/joint_states` is publishing before doing anything else.
- Confirm that both camera topics are active before starting either collection or inference.
- Use twist control only for data collection.
- Use trajectory control for inference.
- Record demonstrations only after all teleop and gripper-control nodes are working correctly.
- Keep naming and topic conventions consistent across recordings so the downstream dataset conversion pipeline remains stable.
- When in doubt, check `ros2 topic list`, `ros2 topic echo [TOPIC_NAME]`, `ros2 action list`, and `ros2 control list_controllers` to verify runtime state.
- Be careful when homing — there is no collision avoidance in the example command.
- If RealSense topics don't match the examples exactly, inspect the live topic list and update commands accordingly.
- Use the `openpi_ros` Python 3.10 environment for ROS runtime control. Do not use the Python 3.11 training environment for `inferenceloopRTC.py`.
```

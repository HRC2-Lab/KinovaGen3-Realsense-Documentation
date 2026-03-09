import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import Joy
from control_msgs.action import GripperCommand
import subprocess


class JoyToGripperClient(Node):

    def __init__(self):
        super().__init__('joy_to_gripper_client')
        self._action_client = ActionClient(self, GripperCommand, '/robotiq_gripper_controller/gripper_cmd')
        self.declare_parameter('input_topic', '/joy')
        self.declare_parameter('open_button', 0)
        self.declare_parameter('close_button', 1)

        self.gripper_position = 0.0
        # Does not work! self.declare_parameter('max_effort', 5.0)
        self._gripper_response = None

        input_topic = self.get_parameter('input_topic').value

        self.subscription = self.create_subscription(
            Joy,
            input_topic,
            self.open_or_close,
            10)
        self.get_logger().info(f'Open/close node initialized, reading from {input_topic}')

    def open_or_close(self, msg):
        # a button opens the gripper fully
        if(msg.buttons[self.get_parameter('open_button').value] == 1):
            if self.gripper_position > 0.0: self.gripper_position -= 0.08
            self.send_goal(self.gripper_position)
        # b button closes the gripper fully
        elif (msg.buttons[self.get_parameter('close_button').value] == 1):
            if self.gripper_position < 0.8: self.gripper_position += 0.08
            self.send_goal(self.gripper_position)

    def send_goal(self, position):
        goal_msg = GripperCommand.Goal()
        goal_msg.command.position = position
        goal_msg.command.max_effort = 0.0 # Does nothing!
        
        self.get_logger().info("Waiting for server...")
        self._action_client.wait_for_server()

        return self._action_client.send_goal_async(goal_msg)
        

def main(args=None):
    rclpy.init(args=args)
    action_client = JoyToGripperClient()
    rclpy.spin(action_client)
    #future = action_client.send_goal(0.8)
    #action_client.get_logger().info("Sent goal of position 0.8")
    #rclpy.spin_until_future_complete(action_client, future)
    #future = action_client.send_goal(0.8)
    #action_client.get_logger().info("Sent goal of position 0.8")
    #rclpy.spin_until_future_complete(action_client, future)
    action_client.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

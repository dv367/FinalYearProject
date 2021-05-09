#!/usr/bin/env python
import rospy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist, Vector3
import autograd.numpy as np
from autograd import grad
from time import time
from multi_robot_mpc.msg import States
import matplotlib.pyplot as plt


state = [2.5, -2.1, 1.57]
init = [-1, 0, 1.57]#[-3.8, -9.7, 1.57]
# state = init
states_x1 = []
states_y1 = []
states_psi1 = []

states_x2 = []
states_y2 = []
states_psi2 = []

states_x3 = []
states_y3 = []
states_psi3 = []

rx0 = 5
rx1 = 0
rx2 = 0
rx3 = 0

v_optimal = 0.0
psidot_optimal = 0.0

class ModelPredictiveControl:

	def __init__(self, x_g, y_g, psi_g, angular_max, linear_max):

		self.horizon = 10
		self.control = 1
		self.dt = 0.25
		self.psidot_max = angular_max
		self.v_max = linear_max
		self.goal = [x_g, y_g]	
		self.pre_states = States()
		self.psi_terminal = psi_g
		self.pub2 = rospy.Publisher('volta_0/pre_state', States, queue_size=10)
		self.stop = 1
		self.job = 0 # follower = 0 leader = 1
		self.te = 0.0
		self.loop = 0.0
		self.v_optimal = 0.0
		self.psidot_optimal = 0.0
		self.obsx = [-2.5, 0.34, 0.34, -1, -2.4]#[-6, -6, -5, -5, -5.5] 
		self.obsy = [0.5, 0.51, -2.27, -0.8, -2.2]#[0.5, 1.5, 1.5, 0.5, 1]
		self.r = [0.2 * np.sqrt(2)/2, 0.2 * np.sqrt(2), 0.2 * np.sqrt(2), 0.2 * np.sqrt(2), 0.2 * np.sqrt(2)]
		self.rr = 0.35
		self.shelfx = [4.73, 4.73, 4.73, 4.73, 4.73, 4.73, 4.4, -0.8, -1.08, -5.79, 0]
		self.shelfy = [-8.66, -6.75, -4.84, -2.93, -1.02, 0.89, 6.67, 9.09, -0.7, -0.95, 0]
		self.shelfa = [3.87, 3.87, 3.87, 3.87, 3.87, 3.87, 4.7, 3.31, 2.9, 2.42, 14]
 		self.shelfb = [0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 7.8, 1.76, 15.87, 18, 21.5] 
		self.wayX = [ 1.76, x_g]
		self.wayY = [ -2.2, y_g]
		self.wayPsi = [0.0, 0.0]
		self.goal = [self.wayX[0], self.wayY[0]]
		self.psi_terminal = self.wayPsi[0]
		l = 1 #square config
		self.config_matrix = [[0, l, 2*l/np.sqrt(2), l], [l, 0, l, 2*l/np.sqrt(2)], [2*l/np.sqrt(2), l, 0, l], [l, 2*l/np.sqrt(2), l, 0]]

	def optimize(self, state, u, mode,steps=12, lr=0.005, decay=0.9, eps=1e-8):

		dx_mean_sqr = np.zeros(self.horizon*2)

		if mode == "solo":
			dF = grad(self.cost_goal_only)
		elif mode == "multi":
			dF = grad(self.cost_maintain_config) 

		startTime = time()
		for k in range(steps):
		    dx = dF(u, state)
		    dx_mean_sqr = decay * dx_mean_sqr + (1.0 - decay) * dx ** 2
		    if k != steps - 1:
				u -= lr * dx / (np.sqrt(dx_mean_sqr) + eps)
				
		self.pub2.publish(self.pre_states)
		self.te += time() - startTime
		self.loop += 1
		# print("robot0", self.te/self.loop)
		return u

	def cost_maintain_config(self, u, state): 

		psi = [state[2] + u[self.horizon] * self.dt]
		rn = [state[0] + u[0] * np.cos(psi[0]) * self.dt]
		re = [state[1] + u[0] * np.sin(psi[0]) * self.dt]

		for i in range(1, self.horizon):
			psi.append(psi[i-1] + u[self.horizon + i] * self.dt)
			rn.append(rn[i-1] + u[i] * np.cos(psi[i]) * self.dt)
			re.append(re[i-1] + u[i] * np.sin(psi[i]) * self.dt)	
		rn = np.array(rn)
		re = np.array(re)
		psi = np.array(psi)
			
		self.pre_states.x = rn._value
		self.pre_states.y = re._value
		self.pre_states.psi = psi._value
		self.pre_states.x0 = state[0]
		self.pre_states.y0 = state[1]
		self.pre_states.psi0 = state[2]
		
		lamda_1 = np.maximum(np.zeros(self.horizon), -0.0*self.v_max - u[:self.horizon]) + np.maximum(np.zeros(self.horizon), u[:self.horizon] - self.v_max) 
		lamda_2 = np.maximum(np.zeros(self.horizon), -self.psidot_max - u[self.horizon:]) + np.maximum(np.zeros(self.horizon), u[self.horizon:] - self.psidot_max) 
		cost_xy = (rn - self.goal[0]) ** 2 + (re - self.goal[1]) ** 2 		
		
		cost_dist = (np.sqrt((states_x1 - rn) ** 2 + (states_y1 - re) ** 2) - self.config_matrix[0][1]) ** 2 + (np.sqrt((states_x2 - rn) ** 2 + (states_y2 - re) ** 2) - self.config_matrix[0][2]) ** 2 + (np.sqrt((states_x3 - rn) ** 2 + (states_y3 - re) ** 2) - self.config_matrix[0][3]) ** 2
		cost_psi = (psi - states_psi1) ** 2
		cost_ = 10000 * lamda_1 + 500 * lamda_2 + 450 * cost_dist + 5 * cost_psi + 15 * cost_psi[-1]+ 10 * self.job * cost_xy 
		
		cost = np.sum(cost_) 

		
		return cost
	
	def cost_goal_only(self, u, state):

		psi = [state[2] + u[self.horizon] * self.dt]
		rn = [state[0] + u[0] * np.cos(psi[0]) * self.dt]
		re = [state[1] + u[0] * np.sin(psi[0]) * self.dt]

		for i in range(1, self.horizon):
			psi.append(psi[i-1] + u[self.horizon + i] * self.dt)
			rn.append(rn[i-1] + u[i] * np.cos(psi[i]) * self.dt)
			re.append(re[i-1] + u[i] * np.sin(psi[i]) * self.dt)	
		rn = np.array(rn)
		re = np.array(re)
		psi = np.array(psi)
		
			
		self.pre_states.x = rn._value
		self.pre_states.y = re._value
		self.pre_states.psi = psi._value
		self.pre_states.x0 = state[0]
		self.pre_states.y0 = state[1]
		self.pre_states.psi0 = state[2]

		lamda_1 = np.maximum(np.zeros(self.horizon), -0*self.v_max - u[:self.horizon]) + np.maximum(np.zeros(self.horizon), u[:self.horizon] - self.v_max) 
		lamda_2 = np.maximum(np.zeros(self.horizon), -self.psidot_max - u[self.horizon:]) + np.maximum(np.zeros(self.horizon), u[self.horizon:] - self.psidot_max) 
		lamda_shelf = np.array([np.maximum(np.zeros(self.horizon), 1 - ((((rn - self.shelfx[i])/(self.shelfa[i]/2 + self.rr))**10 + (((re - self.shelfy[i])/(self.shelfb[i]/2 + self.rr))**10)))) for i in range(len(self.shelfx)-1)], dtype=float)
		lamda_w1 = np.maximum(np.zeros(self.horizon), self.shelfa[-1]/2 - rn) + np.maximum(np.zeros(self.horizon), rn - self.shelfa[-1]/2) 
		lamda_w2 = np.maximum(np.zeros(self.horizon), self.shelfb[-1]/2 - re) + np.maximum(np.zeros(self.horizon), re - self.shelfb[-1]/2) 
		lamda_shelf = np.sum(lamda_shelf, axis = 0) 
		
		cost_xy = (rn - self.goal[0]) ** 2 + (re - self.goal[1]) ** 2
		cost_smoothness_a = (np.hstack((u[0] - self.v_optimal, np.diff(u[0:self.horizon])))/self.dt) ** 2
		cost_smoothness_w = (np.hstack((u[self.horizon] - self.psidot_optimal, np.diff(u[self.horizon:])))/self.dt)**2
		cost_psi = (psi - self.psi_terminal) ** 2
		
		dist_robot1 = np.sqrt((states_x1 - rn) ** 2 + (states_y1 - re) ** 2)
		dist_robot2 = np.sqrt((states_x2 - rn) ** 2 + (states_y2 - re) ** 2)
		# dist_robot3 = np.sqrt((states_x3 - rn) ** 2 + (states_y3 - re) ** 2)
		# cost_robot_obs1 = (1 / dist_robot1) * ((self.rr + 0.5 - dist_robot1)/(abs(self.rr + 0.5 - dist_robot1)+0.000000000001) + 1)
		# cost_robot_obs2 = (1 / dist_robot2) * ((self.rr + 0.5 - dist_robot2)/(abs(self.rr + 0.5 - dist_robot2)+0.000000000001) + 1)
		# cost_robot_obs3 = (1 / dist_robot3) * ((self.rr + 0.5 - dist_robot3)/(abs(self.rr + 0.5 - dist_robot3)+0.000000000001) + 1)
		
		cost_robot_obs2 = np.maximum(np.zeros(self.horizon), -dist_robot2 + 2*self.rr+0.01)
		cost_robot_obs1 = np.maximum(np.zeros(self.horizon), -dist_robot1 + 2*self.rr+0.01) 
		cost_robot_obs = cost_robot_obs1 + cost_robot_obs2 #+ cost_robot_obs3
		# dist_obs = np.array([np.sqrt((rn - np.array(self.obsx[i])) ** 2 + (re - np.array(self.obsy[i])) ** 2) for i in range(len(self.obsx))], dtype=float)
		# cost_obs = ((self.r[0] + self.rr + 0.25 - dist_obs)/(abs(self.r[0] + self.rr + 0.25 - dist_obs)+0.000000000000001) + 1) * (1/dist_obs)
		# cost_obs = np.sum(cost_obs, axis=0)

		cost_ = 100000 * lamda_1 + 250 * lamda_2 + 10000 * (lamda_shelf) + \
				20 * cost_xy + 500 * cost_xy[-1] +  2 * cost_psi + 0 * cost_psi[-1] + \
				1 * cost_smoothness_a + 1 * cost_smoothness_w + 1000 * cost_robot_obs 
		cost = np.sum(cost_) 

		return cost

def statesCallback1(data):
	global states_x1, states_y1, states_psi1, rx1

	states_x1 = data.x
	states_y1 = data.y
	states_psi1 = data.psi
	rx1 = 1
	l = data.l
	myRobot.config_matrix = [[0, l, 2*l/np.sqrt(2), l], [l, 0, l, 2*l/np.sqrt(2)], [2*l/np.sqrt(2), l, 0, l], [l, 2*l/np.sqrt(2), l, 0]]

	

def statesCallback2(data):
	global states_x2, states_y2, states_psi2, rx2

	states_x2 = data.x
	states_y2 = data.y
	states_psi2 = data.psi
	rx2 = 1

	

def statesCallback3(data):
	global states_x3, states_y3, states_psi3, rx3

	states_x3 = data.x
	states_y3 = data.y
	states_psi3 = data.psi
	rx3 = 1

def odomCallback(data):
	global rx0, state, init

	y = data.pose.pose.position.x
	x = -data.pose.pose.position.y

	vy = data.twist.twist.linear.x
	vx = -data.twist.twist.linear.y

	wz = data.twist.twist.angular.z

	qx = data.pose.pose.orientation.x
	qy = data.pose.pose.orientation.y
	qz = data.pose.pose.orientation.z
	qw = data.pose.pose.orientation.w

	siny_cosp = 2 * (qw * qz + qx * qy)
	cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
	psi = np.arctan2(siny_cosp, cosy_cosp)

	psi = init[2] + psi
	if psi > np.pi:
		psi = psi - 2 * np.pi
	elif psi < -np.pi:
		psi = psi + 2 * np.pi

	state[0] = x + init[0]
	state[1] = y + init[1]
	state[2] = psi
	
	if rx0 == 5:
		rx0 = 1

if __name__ == '__main__':
	
	freq = 10
	rospy.init_node('my_robot0', anonymous='True')	
	rospy.Subscriber('volta_0/volta_base_controller/odom', Odometry, odomCallback)

	rospy.Subscriber('volta_1/pre_state', States, statesCallback1)
	rospy.Subscriber('volta_2/pre_state', States, statesCallback2)
	rospy.Subscriber('volta_3/pre_state', States, statesCallback3)
	
	
	pub = rospy.Publisher('volta_0/cmd_vel', Twist, queue_size=10)
	

	rate = rospy.Rate(freq)

	myRobot = ModelPredictiveControl(5.2, -2.2, 0, 5, 1)
	u = np.zeros(2*myRobot.horizon)
	u_psidot = []
	u_v = []
	sim_time = []
	iter = 0
	mode = "multi"
	t = time()
	dist_goal = 1000
	cnt = 1
	while not rospy.is_shutdown():
		
		dist_goal = np.sqrt((state[0] - myRobot.goal[0]) ** 2 + (state[1] - myRobot.goal[1]) ** 2)
		res_x = abs(state[0]- myRobot.goal[0])
		res_y = abs(state[1]- myRobot.goal[1])
		res_psi = abs(state[2]- myRobot.psi_terminal)

		if rx0 == 1.0:
			myRobot.pre_states.x = np.full(myRobot.horizon, state[0])
			myRobot.pre_states.y = np.full(myRobot.horizon, state[1])
			myRobot.pre_states.psi = np.full(myRobot.horizon, state[2])
			myRobot.pub2.publish(myRobot.pre_states)
		if (rx1 and rx2 and rx3 or mode == "solo"):
			rx0 = 0.0				
			iter+=1
			sim_time.append(iter/freq)
			u = myRobot.optimize(state, u, mode)
			myRobot.v_optimal = u[0]
			myRobot.psidot_optimal = u[myRobot.horizon]
			pub.publish(Twist(Vector3(u[0], 0, 0),Vector3(0, 0, u[myRobot.horizon])))
			
		rate.sleep()

	v_max = 1
	psidot_max = 5
	plt.figure(1)
	plt.title('v_controls')
	plt.plot(sim_time, u_v)
	plt.plot([0, sim_time[-1]], [v_max, v_max])
	plt.plot([0, sim_time[-1]], [-v_max, -v_max])
	plt.legend(["linear_velocity", "max_bounds", "min_bounds"], loc ="upper right")

	plt.figure(3)
	plt.title('psidot_controls')
	plt.plot(sim_time, u_psidot)
	plt.plot([0, sim_time[-1]], [psidot_max, psidot_max])
	plt.plot([0, sim_time[-1]], [-psidot_max, -psidot_max])
	plt.legend(["angular_velocity", "max_bounds", "min_bounds"], loc ="upper right")
	# plt.show()
	rospy.spin()

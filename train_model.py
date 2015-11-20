#!/usr/bin/env python
import sys, os
from glob import iglob

from PIL import Image
import numpy as np
import tensorflow as tf

LEARNING_RATE = 0.01
TRAINING_ITERATIONS = 10000
TRAINING_DROPOUT_RATE = 0.8
TRAINING_REPORT_INTERVAL = 100
REPRESENTATION_SIZE = 64
BATCH_SIZE = 5
IMAGE_WIDTH = 256
IMAGE_HEIGHT = 256
IMAGE_DEPTH = 3

def build_encoder(image_batch, keep_prob, representation_size=REPRESENTATION_SIZE):
	# Conv -> Bias -> Pool -> Norm -> Dropout
	batch_shape = image_batch.get_shape()

	# Conv 1
	cw1 = tf.Variable(tf.random_normal([5, 5, batch_shape[3].value, 256]))
	cb1 = tf.Variable(tf.random_normal([256,]))
	conv1 = tf.nn.conv2d(image_batch, filter=cw1, strides=[1, 1, 1, 1], padding='SAME', name="conv1")
	biased1 = tf.nn.bias_add(conv1, cb1) # Special case of +cb1 which is a 1D-Tensor cast.
	act1 = tf.nn.relu(biased1)
	pool1 = tf.nn.max_pool(act1, ksize=[1, 5, 5, 1], strides=[1, 5, 5, 1], padding='SAME')
	norm1 = tf.nn.lrn(pool1, 5, bias=1.0, alpha=0.001 / 9.0, beta=0.75)
	drop1 = tf.nn.dropout(norm1, keep_prob)
	
	# Conv 2
	cw2 = tf.Variable(tf.random_normal([5, 5, batch_shape[3].value, 256]))
	cb2 = tf.Variable(tf.random_normal([256,]))
	conv2 = tf.nn.conv2d(drop1, filter=cw2, strides=[1, 1, 1, 1], padding='SAME', name="conv2")
	biased2 = tf.nn.bias_add(conv2, cb2)
	act2 = tf.nn.relu(biased2)
	pool2 = tf.nn.max_pool(act2, ksize=[1, 5, 5, 1], strides=[1, 5, 5, 1], padding='SAME')
	norm2 = tf.nn.lrn(pool2, 5, bias=1.0, alpha=0.001, beta=0.75)
	drop2 = tf.nn.dropout(norm2, keep_prob)

	# Calculate flat size.
	drop_length = IMAGE_DEPTH*(IMAGE_WIDTH/5/5)*(IMAGE_HEIGHT/5/5)

	# Reshape
	resh1 = tf.reshape(drop2, [-1, drop_length]) # Make flat

	# FC 1
	wf1 = tf.Variable(tf.random_normal([drop_length, representation_size]))
	fb1 = tf.Variable(tf.random_normal([representation_size,]))
	full1 = tf.matmul(resh1, wf1) + fb1
	act3 = tf.nn.relu(full1)

	return act3, [cw1, cw2, wf1], [cb1, cb2, fb1]

def build_decoder(representation_batch, keep_prob, output_shape):
	# FC 2
	wf2 = tf.Variable(tf.random_normal([
		representation_batch.get_shape()[1].value, 
		output_shape[1].value*output_shape[2].value*output_shape[3].value
	]))
	fb2 = tf.Variable(tf.random_normal([output_shape[1].value*output_shape[2].value*output_shape[3].value,]))
	full2 = tf.matmul(representation_batch, wf2) + fb2
	act4 = tf.nn.relu(full2)

	# Reshape
	resh2 = tf.reshape(act4, [-1, output_shape[1].value, output_shape[2].value, output_shape[3].value])

	# Conv 3
	cw3 = tf.Variable(tf.random_normal([5, 5, output_shape[3].value, 1]))
	cb3 = tf.Variable(tf.random_normal([1,]))
	conv3 = tf.nn.conv2d(resh2, filter=cw3, strides=[1, 1, 1, 1], padding='SAME', name="deconv1")
	biased3 = tf.nn.bias_add(conv3, cb3)
	act5 = tf.nn.relu(biased3)
	pool3 = tf.nn.max_pool(act5, ksize=[1, 5, 5, 1], strides=[1, 5, 5, 1], padding='SAME')
	norm3 = tf.nn.lrn(pool3, 5, bias=1.0, alpha=0.001, beta=0.75)
	drop3 = tf.nn.dropout(norm3, keep_prob)

	# Conv 4
	cw4 = tf.Variable(tf.random_normal([5, 5, output_shape[3].value, 1]))
	cb4 = tf.Variable(tf.random_normal([1,]))
	conv4 = tf.nn.conv2d(drop3, filter=cw4, strides=[1, 1, 1, 1], padding='SAME', name="deconv2")
	biased4 = tf.nn.bias_add(conv4, cb4)
	act5 = tf.nn.relu(biased4) # Don't drop last layer.

	return act5, [wf2, cw3, cw4], [fb2, cb3, cb4]

# Define objects
input_batch = tf.placeholder(tf.types.float32, [None, IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_DEPTH])
encoded_batch = tf.placeholder(tf.types.float32, [None, REPRESENTATION_SIZE])
keep_prob = tf.placeholder(tf.types.float32)

encoder, encoder_weights, encoder_biases = build_encoder(input_batch, keep_prob)
autoencoder, ae_weights, ae_biases = build_decoder(encoder, keep_prob, input_batch.get_shape())
decoder, decoder_weights, decoder_biases = build_decoder(encoded_batch, tf.constant(1.0), input_batch.get_shape())

# Define goals
l1_cost = tf.reduce_mean(tf.abs(input_batch - autoencoder))
l2_cost = tf.reduce_sum(tf.pow(input_batch - autoencoder,2))
cost = l2_cost
optimizer = tf.train.AdamOptimizer(learning_rate=LEARNING_RATE).minimize(cost)

# Define data-source iterator
def gather_batch(file_glob, batch_size):
	reader = tf.WholeFileReader()
	while True:
		image_batch = list()
		batch = np.zeros([batch_size, IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_DEPTH], dtype=np.float)
		for index, filename in zip(range(batch_size), iglob(file_glob)):
			img = Image.open(filename)
			batch[index,:,:,:] = np.asarray(img)/255.0
		yield batch
			
# Run!
with tf.Session() as sess:
	generator = gather_batch(sys.argv[1], BATCH_SIZE)
	saver = tf.train.Saver()
	sess.run(tf.initialize_all_variables())
	for iteration in range(TRAINING_ITERATIONS):
		x_batch = generator.next()
		sess.run(optimizer, feed_dict={input_batch:x_batch, keep_prob: TRAINING_DROPOUT_RATE})
		if iteration % TRAINING_REPORT_INTERVAL == 0:
			l1_score, l2_score = sess.run([l1_cost, l2_cost], feed_dict={input_batch:x_batch, keep_prob:1.0})
			print("Iteration {}: L1 {}  L2 {}".format(iteration, l1_score, l2_score))
			saver.save(sess, "checkpoint.model", global_step=iteration)
			#fout = open("example.jpg", 'wb')
			#tf.image.encode_jpg(


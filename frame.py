import os
import cv2
import numpy as np
from scipy.spatial import cKDTree
np.set_printoptions(suppress=True)

from skimage.measure import ransac
from skimage.transform import FundamentalMatrixTransform

from helpers import add_ones, poseRt, fundamentalToRt, normalize

def extractFeatures(img):
  orb = cv2.ORB_create()
  # detection
  pts = cv2.goodFeaturesToTrack(np.mean(img, axis=2).astype(np.uint8), 3000, qualityLevel=0.01, minDistance=7)

  # extraction
  kps = [cv2.KeyPoint(x=f[0][0], y=f[0][1], _size=20) for f in pts]
  kps, des = orb.compute(img, kps)

  # return pts and des
  return np.array([(kp.pt[0], kp.pt[1]) for kp in kps]), des

def match_frames(f1, f2):
  bf = cv2.BFMatcher(cv2.NORM_HAMMING)
  matches = bf.knnMatch(f1.des, f2.des, k=2)

  # Lowe's ratio test
  ret = []
  idx1, idx2 = [], []
  idx1s, idx2s = set(), set()

  for m,n in matches:
    if m.distance < 0.75*n.distance:
      p1 = f1.kps[m.queryIdx]
      p2 = f2.kps[m.trainIdx]

      # be within orb distance 32
      if m.distance < 32:
        # keep around indices
        # TODO: refactor this to not be O(N^2)
        if m.queryIdx not in idx1s and m.trainIdx not in idx2s:
          idx1.append(m.queryIdx)
          idx2.append(m.trainIdx)
          idx1s.add(m.queryIdx)
          idx2s.add(m.trainIdx)
          ret.append((p1, p2))

  # no duplicates
  assert(len(set(idx1)) == len(idx1))
  assert(len(set(idx2)) == len(idx2))

  assert len(ret) >= 8
  ret = np.array(ret)
  idx1 = np.array(idx1)
  idx2 = np.array(idx2)

  # fit matrix
  model, inliers = ransac((ret[:, 0], ret[:, 1]),
                          FundamentalMatrixTransform,
                          min_samples=8,
                          residual_threshold=0.001,
                          max_trials=100)
  print("Matches:  %d -> %d -> %d -> %d" % (len(f1.des), len(matches), len(inliers), sum(inliers)))
  return idx1[inliers], idx2[inliers], fundamentalToRt(model.params)

class Frame(object):
  def __init__(self, mapp, img, K, pose=np.eye(4), tid=None):
    self.K = np.array(K)
    self.pose = np.array(pose)

    if img is not None:
      self.h, self.w = img.shape[0:2]
      self.kpus, self.des = extractFeatures(img)
      self.pts = [None]*len(self.kpus)
    else:
      # fill in later
      self.h, self.w = 0, 0
      self.kpus, self.des, self.pts = None, None, None

    self.id = tid if tid is not None else mapp.add_frame(self)

  # inverse of intrinsics matrix
  @property
  def Kinv(self):
    if not hasattr(self, '_Kinv'):
      self._Kinv = np.linalg.inv(self.K)
    return self._Kinv

  # normalized keypoints
  @property
  def kps(self):
    if not hasattr(self, '_kps'):
      self._kps = normalize(self.Kinv, self.kpus)
    return self._kps

  # KD tree of unnormalized keypoints
  @property
  def kd(self):
    if not hasattr(self, '_kd'):
      self._kd = cKDTree(self.kpus)
    return self._kd


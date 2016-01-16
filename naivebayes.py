import random
import numpy as np
from numpy import log, exp, isnan, isinf, ceil, sum
from sklearn.naive_bayes import MultinomialNB
from sklearn.utils.extmath import logsumexp

### functions for cross-validation of MultinomialNB
def cross_validation(docs, cats, nfolds=10):
    pass

def build_confusion_matrix(nb, test_docs, test_cats):
    pass

def build_crossval_indices(n,k):
    indices = [int(ceil((float(n)/k)*i)) for i in range(k+1)]
    return indices

def get_crossval_split(l, indices, i):
    test_start_idx = indices[i]
    test_end_idx = indices[i+1]

    train_l = l[:test_start_idx] + l[test_end_idx:]
    test_l = l[test_start_idx:test_end_idx]

    return train_l, test_l

def shuffle_paired_lists(l1, l2):
    zipped = zip(l1, l2)
    random.shuffle(zipped)

    unzipped1 = [v[0] for v in zipped]
    unzipped2 = [v[1] for v in zipped]

    return unzipped1, unzipped2


### helper functions for EM
def generate_normed_rand_log_prob(vecshape, count_vec=None, max_alpha=10):
    if count_vec is None:
        rand_prob = np.random.random(vecshape)
    else:
        rand_to_add = ceil(np.random.random(vecshape) * max_alpha)
        rand_prob = count_vec + rand_to_add
    rand_log_prob = log(rand_prob)

    norm_axis = vecshape.index(max(vecshape))
    log_norm = logsumexp(rand_log_prob, norm_axis)
    log_norm_vec = np.resize(log_norm, vecshape)

    normed_rand_log_prob = rand_log_prob - log_norm_vec

    return normed_rand_log_prob

def count_docs_per_class(nb, doc_vec):
    return nb.predict_proba(doc_vec).sum(axis=0)

def count_live_classes(nb,doc_vec):
    docs_per_class = count_docs_per_class(nb,doc_vec)
    return len(docs_per_class.nonzero()[0])


class NaiveBayesEM(object):
    """
    A NaiveBayesEM object handles expectation-maximization for unsupervised
    text classification using the Naive Bayes model.
    This class currently uses the MultinomialNB class from sklearn.naive_bayes

    :param documents: the texts to cluster
    :type documents: array-like, sparse matrix, shape = [n_samples, n_features]

    :param n_categories: the (maximum) number of categories
    :type doc_categories: int

    :param max_iterations: the maximum number of EM iterations to attempt, in
                           case we don't find a local maximum before then
    :type max_iterations: int

    :param randomize: whether to truly truly pseudorandom initial probabilities.
                      if False, parameters are initialized by randomly smoothing over
                      the empirical distribution
                      False is recommended if fit_prior is True; otherwise you're
                      likely to get very fast divergence.
    :type randomize: boolean

    :param **kwargs: other arguments to pass to the MultinomialNB instances
                     (at this writing, can include alpha,class_prior,fit_prior;
                     check sklearn's documentation for your version)

    """

    def __init__(self,
                 documents,
                 n_categories,
                 max_iterations=50,
                 randomize=False,
                 **kwargs):

        self.documents = documents
        self.n_categories = n_categories
        self.max_iterations = max_iterations
        self.randomize = randomize
        self.kwargs = kwargs

        # some shapes and sizes for easy access later
        self.n_samples, self.n_features = self.documents.shape
        self.class_log_prior_shape = (self.n_categories,)
        self.feature_log_prob_shape = (self.n_categories, self.n_features)

        # these will hold the parameters at each iteration
        self.class_log_priors = []
        self.feature_log_probs = []

        # when/how to stop the EM iterations
        self.likelihood = []

    def runEM(self):
        ''' initializes, then iteratively runs, the EM algorithm to cluster
            self.documents in self.n_category different classes '''
        self.initializeEM(self.randomize)

        for iter_n in range(self.max_iterations):
            done = False

            try: prev_likelihood = self.likelihood[-1]
            except IndexError: prev_likelihood = None

            nb = MultinomialNB(**self.kwargs)
            # add faked "classes_" attribute to force it to think it's been trained
            nb.classes_ = np.ndarray((self.n_categories,))
            # and add the random parameters to actually "train" it
            nb.class_log_prior_ = self.class_log_priors[-1]
            nb.feature_log_prob_ = self.feature_log_probs[-1]

            soft_predictions = self.e_step(nb)
            nb = self.m_step(soft_predictions)

            self.last_nb = nb

            ### CHECK LIKELIHOOD CHANGE
            jll = nb._joint_log_likelihood(self.documents)
            best_likelihoods = jll.max(axis=1)
            this_likelihood = sum(best_likelihoods)

            self.likelihood.append(this_likelihood)
            if this_likelihood == prev_likelihood:
                done = True
                pass

            #print iter_n, this_likelihood #, nb.count_classifications()
            #print iter_n, this_likelihood, count_live_classes(nb)
            if done:
                break

    def initializeEM(self, randomize=False):
        if randomize:
            class_log_prior_ = generate_normed_rand_log_prob(self.class_log_prior_shape)
            feature_log_prob_ = generate_normed_rand_log_prob(self.feature_log_prob_shape)

        else:
            uniform_class_counts = np.ones(self.class_log_prior_shape)
            class_log_prior_ = generate_normed_rand_log_prob(self.class_log_prior_shape,
                                                             count_vec=uniform_class_counts,
                                                             max_alpha=0)

            doc_vec_counts = np.resize(self.documents.sum(0), self.feature_log_prob_shape)
            feature_log_prob_ = generate_normed_rand_log_prob(self.feature_log_prob_shape,
                                                              count_vec=doc_vec_counts,
                                                              max_alpha=10)

        self.class_log_priors.append(class_log_prior_)
        self.feature_log_probs.append(feature_log_prob_)

    def e_step(self, nb):
        nb.class_log_prior_ = self.class_log_priors[-1]
        nb.feature_log_prob_ = self.feature_log_probs[-1]

        soft_predictions = nb.predict_proba(self.documents)
        return soft_predictions

    def m_step(self, soft_predictions):
        nb = MultinomialNB(**self.kwargs)

        for category_idx in range(self.n_categories):
            catvec = np.zeros(self.n_samples)
            catvec += category_idx

            cat_weights = soft_predictions.T[category_idx]
            nb.partial_fit(self.documents,
                           catvec,
                           classes=range(self.n_categories),
                           sample_weight=cat_weights)

        self.class_log_priors.append(nb.class_log_prior_)
        self.feature_log_probs.append(nb.feature_log_prob_)

        return nb

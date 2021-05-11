import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from typing import Union

from . import utils

# ----------------------------------------------------------------------------------------------------------------
# Heads (feature extractors)
# ----------------------------------------------------------------------------------------------------------------

class Base_Net(nn.Module):
    def __init__(self, input_dims, hidden_units):
        super().__init__()
        self.input_dims = input_dims
        self.hidden_units = hidden_units

class NatureCNN_Net(Base_Net):
    """ Takes stacked frames as input, and outputs features.
        Based on https://www.cs.toronto.edu/~vmnih/docs/dqn.pdf
    """

    def __init__(self, input_dims, hidden_units=512, norm_layer=None):

        super().__init__(input_dims, hidden_units)

        input_channels = input_dims[0]

        self.conv1 = nn.Conv2d(input_channels, 32, kernel_size=(8,8), stride=(4,4))
        self.conv2 = nn.Conv2d(32, 64, kernel_size=(4,4), stride=(2,2))
        self.conv3 = nn.Conv2d(64, 64, kernel_size=(3,3), stride=(1,1))

        fake_input = torch.zeros((1, *input_dims))
        _, c, w, h = self.conv3(self.conv2(self.conv1(fake_input))).shape

        self.out_shape = (c, w, h)
        self.d = utils.prod(self.out_shape)
        self.hidden_units = hidden_units
        if self.hidden_units > 0:
            self.fc = nn.Linear(self.d, hidden_units)

    def forward(self, x):
        """ forwards input through model, returns features (without relu) """
        N = len(x)
        D = self.d
        x1 = F.relu(self.conv1(x))
        x2 = F.relu(self.conv2(x1))
        x3 = F.relu(self.conv3(x2))
        x4 = torch.reshape(x3, [N,D])
        if self.hidden_units > 0:
            x5 = self.fc(x4)
            return x5
        else:
            return x4


class RNDTarget_Net(Base_Net):
    """ Used to predict output of random network.
        see https://github.com/openai/random-network-distillation/blob/master/policies/cnn_policy_param_matched.py
        for details.
    """

    def __init__(self, input_dims, hidden_units=512):

        super().__init__(input_dims, hidden_units)

        input_channels = input_dims[0]

        self.conv1 = nn.Conv2d(input_channels, 32, kernel_size=(8, 8), stride=(4, 4))
        self.conv2 = nn.Conv2d(32, 64, kernel_size=(4, 4), stride=(2, 2))
        self.conv3 = nn.Conv2d(64, 64, kernel_size=(3, 3), stride=(1, 1))

        fake_input = torch.zeros((1, *input_dims))
        _, c, w, h = self.conv3(self.conv2(self.conv1(fake_input))).shape

        self.out_shape = (c, w, h)
        self.d = utils.prod(self.out_shape)
        self.out = nn.Linear(self.d, hidden_units)

        # we scale the weights so the output varience is about right. The sqrt2 is because of the relu,
        # bias is disabled as per OpenAI implementation.
        # I found I need to bump this up a little to get the varience required (0.4)
        # maybe this is due to weight initialization differences between TF and Torch?
        scale_weights(self, weight_scale=np.sqrt(2)*1.3, bias_scale=0.0)

    def forward(self, x):
        """ forwards input through model, returns features (without relu) """
        N = len(x)
        D = self.d

        x = F.leaky_relu(self.conv1(x), 0.2)
        x = F.leaky_relu(self.conv2(x), 0.2)
        x = F.leaky_relu(self.conv3(x), 0.2)
        x = torch.reshape(x, [N,D])
        x = self.out(x)
        return x


class RNDPredictor_Net(Base_Net):
    """ Used to predict output of random network.
        see https://github.com/openai/random-network-distillation/blob/master/policies/cnn_policy_param_matched.py
        for details.
    """

    def __init__(self, input_dims, hidden_units=512):

        super().__init__(input_dims, hidden_units)

        input_channels = input_dims[0]

        self.conv1 = nn.Conv2d(input_channels, 32, kernel_size=(8, 8), stride=(4, 4))
        self.conv2 = nn.Conv2d(32, 64, kernel_size=(4, 4), stride=(2, 2))
        self.conv3 = nn.Conv2d(64, 64, kernel_size=(3, 3), stride=(1, 1))

        fake_input = torch.zeros((1, *input_dims))
        _, c, w, h = self.conv3(self.conv2(self.conv1(fake_input))).shape

        self.out_shape = (c, w, h)
        self.d = utils.prod(self.out_shape)
        self.fc1 = nn.Linear(self.d, 512)
        self.fc2 = nn.Linear(512, 512)
        self.out = nn.Linear(512, hidden_units)

        # we scale the weights so the output varience is about right. The sqrt2 is because of the relu,
        # bias is disabled as per OpenAI implementation.
        scale_weights(self, weight_scale=np.sqrt(2)*1.3, bias_scale=0.0)

    def forward(self, x):
        """ forwards input through model, returns features (without relu) """
        N = len(x)
        D = self.d
        x = F.leaky_relu(self.conv1(x), 0.2)
        x = F.leaky_relu(self.conv2(x), 0.2)
        x = F.leaky_relu(self.conv3(x), 0.2)
        x = torch.reshape(x, [N,D])
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.out(x)
        return x

# ----------------------------------------------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------------------------------------------

class DualNet(nn.Module):
    """
    Network has both policy and value heads, but may only use one of these.
    """

    def __init__(
            self,
            network,
            input_dims,
            tvf_activation,
            tvf_hidden_units,
            tvf_horizon_transform,
            tvf_time_transform,
            tvf_max_horizon,
            tvf_n_value_heads: int = 1,
            actions=None,
            policy_head=True,
            value_head=True,

            **kwargs
    ):
        super().__init__()

        self.encoder = construct_network(network, input_dims, **kwargs)

        self.policy_head = policy_head
        self.value_head = value_head
        self.tvf_max_horizon = tvf_max_horizon

        if self.policy_head:
            assert actions is not None
            # policy outputs policy, but also value so that we can train it to predict value as an aux task
            # value outputs extrinsic and intrinsic value
            self.policy_net_policy = nn.Linear(self.encoder.hidden_units, actions)
            self.policy_net_value = nn.Linear(self.encoder.hidden_units, 2)

        if self.value_head:

            if tvf_n_value_heads < 0:
                self.n_value_heads = -tvf_n_value_heads
                self.tvf_blending = True
            else:
                self.n_value_heads = tvf_n_value_heads
                self.tvf_blending = False

            self.tvf_activation = tvf_activation
            self.tvf_hidden_units = int(tvf_hidden_units)
            self.horizon_transform = tvf_horizon_transform
            self.time_transform = tvf_time_transform

            # value net outputs a basic value estimate as well as the truncated value estimates (for extrinsic only)
            self.value_net_value = nn.Linear(self.encoder.hidden_units, 2)
            self.value_net_hidden = nn.Linear(self.encoder.hidden_units, self.tvf_hidden_units)
            self.value_net_hidden_aux = nn.Linear(2, self.tvf_hidden_units, bias=False)
            self.value_net_tvf = nn.Linear(self.tvf_hidden_units, self.n_value_heads)

            # because we are adding aux to hidden we want the weight initialization to be roughly the same scale
            torch.nn.init.uniform_(
                self.value_net_hidden_aux.weight,
                -1/(self.encoder.hidden_units ** 0.5),
                 1/(self.encoder.hidden_units ** 0.5)
            )
            if self.value_net_hidden_aux.bias is not None:
                torch.nn.init.uniform_(
                    self.value_net_hidden_aux.bias,
                    -1 / (self.encoder.hidden_units ** 0.5),
                    1 / (self.encoder.hidden_units ** 0.5)
                )

    @property
    def tvf_activation_function(self):
        if self.tvf_activation == "relu":
            return F.relu
        elif self.tvf_activation == "tanh":
            return F.tanh
        elif self.tvf_activation == "sigmoid":
            return F.sigmoid
        else:
            raise Exception("invalid activation")

    def forward(
            self, x, aux_features=None, policy_temperature=1.0,
            exclude_value=False, exclude_policy=False,
        ):
        """
        x is [B, *state_shape]
        aux_features, if given are [B, H, 2] where [...,0] are horizons and [...,1] are fractions of remaining time
        """

        result = {}
        features = F.relu(self.encoder(x))

        if self.policy_head and not exclude_policy:
            unscaled_policy = self.policy_net_policy(features)
            result['raw_policy'] = unscaled_policy
            result['log_policy'] = F.log_softmax(unscaled_policy / policy_temperature, dim=1)

        if self.value_head and not exclude_value:

            value_values = self.value_net_value(features)
            result['ext_value'] = value_values[:, 0]
            result['int_value'] = value_values[:, 1]

            # auxiliary features
            if aux_features is not None:

                # upload aux_features to GPU and cast to float
                if type(aux_features) is np.ndarray:
                    aux_features = torch.from_numpy(aux_features)

                aux_features = aux_features.to(device=value_values.device, dtype=torch.float32)
                _, H, _ = aux_features.shape

                # spread heads out over range, first head is always h=0 and last head is h=tvf_max_horizon
                if self.n_value_heads == 1:
                    scale_factor = 1.0
                else:
                    scale_factor = np.log2(1+self.tvf_max_horizon) / (self.n_value_heads-1)

                # in multi head work out which head predicts which horizon
                log2_horizon = torch.log2(1 + aux_features[..., 0]) / scale_factor

                def get_tvf_values(features, aux_features, horizon_offsets=None):
                    if horizon_offsets is None:
                        horizon_offsets = 0.0
                    transformed_aux_features = torch.zeros_like(aux_features)
                    transformed_aux_features[:, :, 0] = self.horizon_transform(aux_features[:, :, 0]) - horizon_offsets
                    transformed_aux_features[:, :, 1] = self.time_transform(aux_features[:, :, 1])

                    features_part = self.value_net_hidden(features)
                    aux_part = self.value_net_hidden_aux(transformed_aux_features)
                    tvf_h = self.tvf_activation_function(features_part[:, None, :] + aux_part)
                    return self.value_net_tvf(tvf_h)

                def get_head_location(heads, transform=True):
                    locations = ((2 ** (heads * scale_factor)) - 1).to(dtype=torch.float32)
                    if transform:
                        locations = self.horizon_transform(locations)
                    return locations

                if self.tvf_blending:
                    head_low = torch.clamp(torch.floor(log2_horizon), 0, self.n_value_heads - 1).to(dtype=torch.int64)
                    head_high = torch.clamp(torch.ceil(log2_horizon), 0, self.n_value_heads - 1).to(dtype=torch.int64)
                    head_factor = torch.frac(log2_horizon)

                    # it's a shame but we run this twice, once for each centered h_value...
                    # if we where not centering transformed_h we wouldn't have to do this
                    tvf_values_low = get_tvf_values(features, aux_features, get_head_location(head_low))
                    tvf_values_high = get_tvf_values(features, aux_features, get_head_location(head_high))

                    value_low = torch.gather(tvf_values_low, dim=2, index=head_low[:, :, None])[:, :, 0]
                    value_high = torch.gather(tvf_values_high, dim=2, index=head_high[:, :, None])[:, :, 0]
                    result['tvf_value'] = value_low * (1 - head_factor) + value_high * head_factor
                else:
                    head_near = torch.clamp(torch.round(log2_horizon), 0, self.n_value_heads - 1).to(dtype=torch.int64)
                    tvf_values = get_tvf_values(
                        features,
                        aux_features,
                        get_head_location(head_near, transform=self.n_value_heads > 1)
                    )
                    value_near = torch.gather(tvf_values, dim=2, index=head_near[:, :, None])[:, :, 0]
                    result['tvf_value'] = value_near

        return result


class TVFModel(nn.Module):
    """
    Truncated Value Function model
    based on PPG, and (optionaly) using RND

    network: the network to use, [nature_cnn]
    input_dims: tuple containing input dims with channels first, e.g. (4, 84, 84)
    actions: number of actions
    device: device to use for model
    dtype: dtype to use for model

    use_rnd: enables random network distilation for exploration
    use_rnn: enables recurrent model (not implemented yet)

    tvf_horizon_transform: transform to use on horizons before input.
    tvf_hidden_units: number of hidden units to use on FC layer before output
    tvf_activation: activation to use on TVF FC layer

    network_args: dict containing arguments for network

    """
    def __init__(
            self,
            network: str,
            input_dims: tuple,
            actions: int,
            device: str = "cuda",
            dtype: torch.dtype=torch.float32,

            use_rnd:bool = False,
            use_rnn:bool = False,

            tvf_max_horizon:int = 65536,
            tvf_horizon_transform = lambda x : x,
            tvf_time_transform = lambda x: x,
            tvf_hidden_units:int = 512,
            tvf_activation:str = "relu",
            tvf_n_value_heads:int=1,

            network_args:Union[dict, None] = None,
    ):

        assert not use_rnn, "RNN not supported yet"

        super().__init__()

        self.input_dims = input_dims
        self.actions = actions
        self.device = device
        self.dtype = dtype

        self.name = "PPG-" + network
        single_channel_input_dims = (1, *input_dims[1:])
        self.use_rnd = use_rnd

        make_net = lambda : DualNet(
            network=network,
            input_dims=input_dims,
            tvf_activation=tvf_activation,
            tvf_hidden_units=tvf_hidden_units,
            tvf_horizon_transform=tvf_horizon_transform,
            tvf_time_transform=tvf_time_transform,
            tvf_n_value_heads=tvf_n_value_heads,
            tvf_max_horizon=tvf_max_horizon,
            actions=actions,
            **(network_args or {})
        )

        self.policy_net = make_net()
        self.value_net = make_net()

        if self.use_rnd:
            self.prediction_net = RNDPredictor_Net(single_channel_input_dims)
            self.target_net = RNDTarget_Net(single_channel_input_dims)
            self.obs_rms = utils.RunningMeanStd(shape=single_channel_input_dims)
            self.features_mean = 0
            self.features_std = 0

        self.set_device_and_dtype(device, dtype)

    def log_policy(self, x, state=None):
        """ Returns detached log_policy for given input. """
        return self.forward(x, state, output="policy")["log_policy"].detach().cpu().numpy()

    def perform_normalization(self, x):
        """
        Applies normalization transform, and updates running mean / std.
        """

        # update normalization constants
        if type(x) is torch.Tensor:
            x = x.cpu().numpy()

        assert x.dtype == np.uint8

        x = np.asarray(x[:, 0:1], np.float32)
        self.obs_rms.update(x)
        mu = torch.tensor(self.obs_rms.mean.astype(np.float32)).to(self.device)
        sigma = torch.tensor(self.obs_rms.var.astype(np.float32) ** 0.5).to(self.device)

        # normalize x
        x = torch.tensor(x).to(self.device)
        x = torch.clamp((x - mu) / (sigma + 1e-5), -5, 5)

        # note: clipping reduces the std down to 0.3 so we multiply the output so that it is roughly
        # unit normal.
        x *= 3.0

        return x

    def set_device_and_dtype(self, device, dtype):
        """
        Set the device and type for model
        """
        self.to(device)
        if dtype == torch.half:
            self.half()
        elif dtype == torch.float:
            self.float()
        elif dtype == torch.double:
            self.double()
        else:
            raise Exception("Invalid dtype {} for model.".format(dtype))

        self.device, self.dtype = device, dtype

    def prediction_error(self, x):
        """ Returns prediction error for given state. """

        # only need first channel for this.
        x = self.perform_normalization(x)

        # random features have too low varience due to weight initialization being different from the OpenAI implementation
        # we adjust it here by simply multiplying the output to scale the features to have a max of around 3
        random_features = self.target_net.forward(x).detach()
        predicted_features = self.prediction_net.forward(x)

        # note: I really want to normalize these... otherwise scale just makes such a difference.
        # or maybe tanh the features?

        self.features_mean = float(random_features.mean().detach().cpu())
        self.features_var = float(random_features.var(axis=0).mean().detach().cpu())
        self.features_max = float(random_features.abs().max().detach().cpu())

        errors = (random_features - predicted_features).pow(2).mean(axis=1)

        return errors

    def forward(self, x, aux_features=None, output: str = "default", policy_temperature: float = 1.0):
        """

        Forward input through model and return dictionary containing

            log_policy: log policy
            policy_int_value: policy networks intrinsic value estimate
            policy_ext_value: policy networks extrinsic value estimate

            int_value: intrinsic value estimate
            ext_value: extrinsic value estimate (often trained as most distant horizon estimate)
            tvf_value: (if horizons given) truncated horizon value estimates

        x: tensor of dims [B, *obs_shape]
        aux_features: (optional) int32 tensor of dims [B, H]
        output: which network(s) to run ["both", "policy", "value"]

        Outputs are:
            policy: policy->policy
            value: value->value
            default: policy->policy, value->value
            full: policy->policy, value->value, value->policy, policy->value (with prefix)
        """

        assert output in ["default", "full", "policy", "value"]

        result = {}
        x = self.prep_for_model(x)

        if output == "full":
            # this is a special case where we return all heads from both networks
            # required for distillation.
            policy_part = self.policy_net(x, aux_features=aux_features, policy_temperature=policy_temperature)
            value_part = self.value_net(x, aux_features=aux_features, policy_temperature=policy_temperature)
            result = {}
            for k,v in policy_part.items():
                result["policy_" + k] = v
            for k, v in value_part.items():
                result["value_" + k] = v
            return result

        if output in ["default", "policy"]:
            result.update(self.policy_net(
                x,
                aux_features=aux_features,
                policy_temperature=policy_temperature,
                exclude_value=True,
            ))
        if output in ["default", "value"]:
            result.update(self.value_net(
                x,
                aux_features=aux_features,
                policy_temperature=policy_temperature,
                exclude_policy=True,
                ))

        return result

    def prep_for_model(self, x, scale_int=True):
        """ Converts data to format for model (i.e. uploads to GPU, converts type).
            Can accept tensor or ndarray.
            scale_int scales uint8 to [0..1]
         """

        assert self.device is not None, "Must call set_device_and_dtype."

        validate_dims(x, (None, *self.input_dims))

        # if this is numpy convert it over
        if type(x) is np.ndarray:
            x = torch.from_numpy(x)

        # move it to the correct device
        x = x.to(self.device, non_blocking=True)

        # then covert the type (faster to upload uint8 then convert on GPU)
        if x.dtype == torch.uint8:
            x = x.to(dtype=self.dtype, non_blocking=True)
            if scale_int:
                x = x / 255
        elif x.dtype == self.dtype:
            pass
        else:
            raise Exception("Invalid dtype {}".format(x.dtype))
        return x



# ----------------------------------------------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------------------------------------------

def construct_network(head_name, input_dims, **kwargs) -> Base_Net:
    head_name = head_name.lower()
    if head_name == "nature":
        return NatureCNN_Net(input_dims, **kwargs)
    else:
        raise Exception("No model head named {}".format(head_name))


def validate_dims(x, dims, dtype=None):
    """ Makes sure x has the correct dims and dtype.
        None will ignore that dim.
    """

    if dtype is not None:
        assert x.dtype == dtype, "Invalid dtype, expected {} but found {}".format(str(dtype), str(x.dtype))

    assert len(x.shape) == len(dims), "Invalid dims, expected {} but found {}".format(dims, x.shape)

    assert all((a is None) or a == b for a,b in zip(dims, x.shape)), "Invalid dims, expected {} but found {}".format(dims, x.shape)


def get_CNN_output_size(input_size, kernel_sizes, strides, max_pool=False):
    """ Calculates CNN output size, if max_pool is true uses max_pool instead of stride."""
    size = input_size
    for kernel_size, stride in zip(kernel_sizes, strides):

        if max_pool:
            size = (size - (kernel_size - 1) - 1) // 1 + 1
            size = size // stride
        else:
            size = (size - (kernel_size - 1) - 1) // stride + 1
    return size

def scale_weights(model: nn.Module, weight_scale, bias_scale):
    for child in model.children():
        child.weight.data *= weight_scale
        child.bias.data *= bias_scale

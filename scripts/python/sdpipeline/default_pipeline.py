import diffusers
from imp import reload
reload(diffusers)

import mlops_utils
import mlops_image_utils
import torch
from . import schedulers_lookup
import numpy
import os

def run(
    model,
    cache_only,
    inference_steps,
    guidance_scale,
    image_deviation,
    input_scheduler,
    input_embeddings,
    controlnet_geo,
    latent_dimension,
):

    dtype = torch.float16

    controlnet_models = []
    controlnet_images = []
    controlnet_scales = []

    if controlnet_geo:
        for point in controlnet_geo.points():
            controlnetmodel = point.stringAttribValue("model")
            geo = point.prims()[0].getEmbeddedGeometry()
            controlnet_conditioning_scale = point.attribValue("scale")
            input_colors = mlops_image_utils.colored_points_to_numpy_array(geo)

            controlnet_conditioning_image = torch.from_numpy(
                numpy.array([input_colors])
            ).to(dtype)

            controlnet = diffusers.ControlNetModel.from_pretrained(
                controlnetmodel,
                local_files_only=cache_only,
                torch_dtype=dtype,
            )

            controlnet_models.append(controlnet)
            controlnet_images.append(controlnet_conditioning_image)
            controlnet_scales.append(controlnet_conditioning_scale)

    text_embeddings = torch.from_numpy(numpy.array([numpy.array(input_embeddings["conditional_embedding"]).reshape(
        input_embeddings["tensor_shape"])]))

    uncond_embeddings = torch.from_numpy(numpy.array([numpy.array(input_embeddings["unconditional_embedding"]).reshape(
        input_embeddings["tensor_shape"])]))


    input_noise = torch.from_numpy(numpy.array([input_scheduler["noise_latent"].reshape(
                    4, latent_dimension[1], latent_dimension[0])])).to(dtype)

    init_latents = numpy.array([input_scheduler["numpy_image"]])
    init_latents = torch.from_numpy(init_latents).to(dtype) / 0.5 - 1.0

    mask_latents = numpy.array([[input_scheduler["numpy_mask"][0]]])
    mask_latents[mask_latents < 0.5] = 0
    mask_latents[mask_latents >= 0.5] = 1
    mask_latents = torch.from_numpy(mask_latents)

    model_path = mlops_utils.ensure_huggingface_model_local(model, os.path.join("$MLOPS", "data", "models", "diffusers"), cache_only)

    # scheduler_config = input_scheduler["config"]
    # scheduler_type = scheduler_config["type"]
    # del scheduler_config["init_timesteps"]
    # del scheduler_config["type"]
    # scheduler = schedulers_lookup.schedulers[scheduler_type].from_config(scheduler_config)

    pipe = diffusers.StableDiffusionControlNetInpaintPipeline.from_pretrained(
        model_path,  controlnet=controlnet_models, torch_dtype=dtype)#, scheduler=scheduler

    pipe.enable_model_cpu_offload()

    out_latent = pipe(
        prompt_embeds = text_embeddings,
        negative_prompt_embeds = uncond_embeddings,
        num_inference_steps=inference_steps,
        guidance_scale = guidance_scale,
        eta=1.0,
        latents = input_noise,
        image=init_latents,
        mask_image=mask_latents,
        control_image=controlnet_images,
        controlnet_conditioning_scale=controlnet_scales,
        output_type = "pil",
        generator = torch.manual_seed(1),
        # TODO: FIX the clamping below. Should not be there, but the solve throws an error otherwise
        strength= max(0.05, image_deviation)
    ).images[0]

    return out_latent

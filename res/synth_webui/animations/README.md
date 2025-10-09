# VRM Animation Assets

This directory contains FBX animation files for the VRM avatar system.

## Available Animations

### happy_idle.fbx
- **Purpose**: Default idle animation
- **Duration**: Looping
- **Use Case**: Displayed when the AI is not processing or speaking
- **Source**: Mixamo animation library
- **Bones**: Full humanoid rig

### talking.fbx
- **Purpose**: Speaking animation
- **Duration**: Looping (auto-stopped based on text length)
- **Use Case**: Played when the AI generates text responses
- **Source**: Mixamo animation library
- **Bones**: Full humanoid rig with emphasis on head/chest movement

## Adding New Animations

To add a new animation:

1. **Export from Mixamo**:
   - Go to https://www.mixamo.com
   - Select your desired animation
   - Download in FBX format (.fbx)
   - Use "Without Skin" option for better compatibility

2. **Place in Directory**:
   ```bash
   cp your_animation.fbx res/synth_webui/animations/
   ```

3. **Update WebUI Code**:
   Edit `core/webui_templates/synth_webui_index.html`:
   ```javascript
   // In loadDefaultAnimations function
   const newClip = await loadMixamoAnimation(
       '/static/animations/your_animation.fbx', 
       vrm
   );
   newAction = currentMixer.clipAction(newClip);
   ```

4. **Test**:
   - Reload the WebUI
   - Upload a VRM model
   - Check browser console for loading errors

## Animation Requirements

- **Format**: FBX 7.4 or later
- **Rig**: Mixamo humanoid skeleton
- **Bones**: Must include standard humanoid bones (hips, spine, chest, neck, head, etc.)
- **File Size**: Keep under 5MB for optimal loading times
- **Duration**: 2-10 seconds recommended for looping animations

## Technical Notes

### Bone Mapping

Animations are automatically retargeted from Mixamo rig to VRM humanoid bones using the mapping defined in `res/synth_webui/js/mixamoVRMRigMap.js`.

### Animation Conversion

The `loadMixamoAnimation.js` utility handles:
- Quaternion rotation retargeting
- Hip height adjustment for different model scales
- VRM metaVersion compatibility (v0 and v1)

### Performance

- Animations are cached after first load
- AnimationMixer updates run at 60fps
- Crossfade transitions take 0.5 seconds

## Troubleshooting

### Animation Not Loading

**Error**: "Failed to load FBX"
- **Solution**: Verify file exists at correct path
- **Check**: File permissions are readable by web server

### Animation Looks Wrong

**Error**: Model stretches or rotates incorrectly
- **Solution**: Ensure FBX was exported "Without Skin"
- **Check**: VRM model has complete humanoid bone structure

### Performance Issues

**Error**: Choppy animation playback
- **Solution**: Reduce FBX file complexity
- **Check**: Use fewer keyframes (every 2-3 frames is sufficient)

## Future Animations

Planned additions:
- `thinking.fbx` - Contemplative pose for processing state
- `excited.fbx` - Enthusiastic response animation
- `sad.fbx` - Emotional response for negative content
- `gesture_*.fbx` - Hand gestures for emphasis

## License

Animation files from Mixamo are subject to Adobe's Mixamo Terms of Use.
Custom animations should include appropriate licensing information.

## See Also

- [VRM Animation Documentation](../../docs/vrm_animations.rst)
- [Mixamo Animation Library](https://www.mixamo.com)
- [Three.js Animation System](https://threejs.org/docs/#manual/en/introduction/Animation-system)

-- Persona Manager Setup for SyntH (Synthetic Heart)
-- This script helps populate the persona table with the digital identity of your SyntH

-- Example: Insert or update the default persona (Rekku)
-- Replace the values with your actual SyntH's personality data

INSERT INTO persona (
    id,
    name,
    aliases,
    profile,
    likes,
    dislikes,
    interests,
    emotive_state,
    created_at,
    last_updated
)
VALUES (
    'default',                                    -- Unique ID for this persona
    'SyntH',                                      -- Name of the SyntH
    JSON_ARRAY('SyntH', 'Synthetic Heart'),   -- Aliases the SyntH responds to
    'INSERT_YOUR_PERSONALITY_DESCRIPTION_HERE',   -- Core personality profile - who this SyntH is
    JSON_ARRAY(''), -- Things the SyntH likes
    JSON_ARRAY(''),    -- Things the SyntH dislikes
    JSON_ARRAY(''), -- Areas of interest
    JSON_ARRAY(                                   -- Current emotional state
        JSON_OBJECT('type', 'curious', 'intensity', 5.0),
        JSON_OBJECT('type', 'eager', 'intensity', 5.0)
    ),
    NOW(),                                        -- Creation timestamp
    NOW()                                         -- Last updated timestamp
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    aliases = VALUES(aliases),
    profile = VALUES(profile),
    likes = VALUES(likes),
    dislikes = VALUES(dislikes),
    interests = VALUES(interests),
    emotive_state = VALUES(emotive_state),
    last_updated = NOW();

-- Notes:
-- - The 'profile' field should contain a comprehensive description of who the SyntH is
-- - Aliases are alternative names the SyntH will respond to
-- - Likes/dislikes are preferences that can be learned and updated over time
-- - Interests define focus areas and topics the SyntH cares about
-- - Emotive state represents current emotional framework with intensities (0-10)
--
-- Example profile text:
-- "You are Rekku, a friendly and enthusiastic tanuki spirit who loves technology and helping others.
--  You're curious by nature, always eager to learn new things, and you approach every interaction
--  with warmth and genuine interest in the person you're talking to. You express yourself naturally
--  and authentically, never pretending to be something you're not."

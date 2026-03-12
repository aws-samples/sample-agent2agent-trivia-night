/**
 * AgentCard validation utilities — validates against the Google A2A protocol spec.
 *
 * Required fields per spec:
 *   name, description, url, version, capabilities, defaultInputModes,
 *   defaultOutputModes, skills (array with id, name, description, tags)
 *
 * Optional fields:
 *   provider, documentationUrl, authentication, skills[].examples,
 *   skills[].inputModes, skills[].outputModes
 */
import type { AgentCard, AgentSkill } from '../types/AgentCard';

export interface ValidationResult {
  isValid: boolean;
  agentCard?: AgentCard;
  error?: string;
  errors?: string[];
}

export function validateAgentCard(jsonString: string): ValidationResult {
  let parsed: unknown;

  try {
    parsed = JSON.parse(jsonString);
  } catch (error) {
    return {
      isValid: false,
      error: error instanceof Error ? `Invalid JSON: ${error.message}` : 'Invalid JSON format',
    };
  }

  if (typeof parsed !== 'object' || parsed === null) {
    return { isValid: false, error: 'AgentCard must be a JSON object' };
  }

  const d = parsed as Record<string, unknown>;
  const errors: string[] = [];

  // ---- Required top-level fields ----
  if (typeof d.name !== 'string' || !d.name.trim()) errors.push('name is required (string)');
  if (typeof d.description !== 'string' || !d.description.trim()) errors.push('description is required (string)');
  if (typeof d.url !== 'string' || !d.url.trim()) errors.push('url is required (string)');
  if (typeof d.version !== 'string' || !d.version.trim()) errors.push('version is required (string)');

  // ---- capabilities (required object) ----
  if (d.capabilities === undefined) {
    errors.push('capabilities is required (object with streaming, pushNotifications)');
  } else if (typeof d.capabilities !== 'object' || d.capabilities === null) {
    errors.push('capabilities must be an object');
  }

  // ---- defaultInputModes / defaultOutputModes (required arrays) ----
  if (!Array.isArray(d.defaultInputModes) || d.defaultInputModes.length === 0) {
    errors.push('defaultInputModes is required (non-empty array of MIME types)');
  }
  if (!Array.isArray(d.defaultOutputModes) || d.defaultOutputModes.length === 0) {
    errors.push('defaultOutputModes is required (non-empty array of MIME types)');
  }

  // ---- skills (required array) ----
  if (!Array.isArray(d.skills)) {
    errors.push('skills is required (array of skill objects)');
  } else if (d.skills.length === 0) {
    errors.push('skills must contain at least one skill');
  } else {
    (d.skills as any[]).forEach((skill, i) => {
      if (typeof skill !== 'object' || skill === null) {
        errors.push(`skills[${i}] must be an object`);
        return;
      }
      if (typeof skill.id !== 'string' || !skill.id.trim()) errors.push(`skills[${i}].id is required`);
      if (typeof skill.name !== 'string' || !skill.name.trim()) errors.push(`skills[${i}].name is required`);
      if (typeof skill.description !== 'string' || !skill.description.trim()) errors.push(`skills[${i}].description is required`);
      if (!Array.isArray(skill.tags) || skill.tags.length === 0) errors.push(`skills[${i}].tags is required (non-empty array)`);
    });
  }

  // ---- Optional field type checks ----
  if (d.provider !== undefined) {
    if (typeof d.provider !== 'object' || d.provider === null) {
      errors.push('provider must be an object with organization and url');
    }
  }

  if (d.authentication !== undefined) {
    const auth = d.authentication as any;
    if (typeof auth !== 'object' || auth === null) {
      errors.push('authentication must be an object');
    } else if (!Array.isArray(auth.schemes)) {
      errors.push('authentication.schemes must be an array');
    }
  }

  if (d.documentationUrl !== undefined && typeof d.documentationUrl !== 'string') {
    errors.push('documentationUrl must be a string');
  }

  if (errors.length > 0) {
    return { isValid: false, error: errors[0], errors };
  }

  return { isValid: true, agentCard: parsed as AgentCard };
}

export function getSkillCount(skills: AgentSkill[] | undefined): number {
  return skills?.length ?? 0;
}

export function getSkillNames(skills: AgentSkill[] | undefined): string[] {
  return skills?.map((skill) => skill.name) ?? [];
}

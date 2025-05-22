import { useState, useCallback, useEffect } from 'react';
import { useWorkspace } from './useWorkspace';

interface RagResponse {
  chunk?: string;
  done?: boolean;
  sources?: Array<{
    uri: string;
    score: number;
  }>;
  prompt_version?: string;
}

interface UseRagStreamOptions {
  onError?: (error: Error) => void;
  onComplete?: (sources: RagResponse['sources'], promptVersion: string) => void;
}

export function useRagStream(options: UseRagStreamOptions = {}) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [response, setResponse] = useState<string>('');
  const [sources, setSources] = useState<RagResponse['sources']>([]);
  const [promptVersion, setPromptVersion] = useState<string>('');
  const workspace = useWorkspace();

  // Check for TextDecoderStream support
  const hasTextDecoderStream = typeof TextDecoderStream !== 'undefined';

  const streamResponse = useCallback(async (url: string, body: any) => {
    setIsLoading(true);
    setError(null);
    setResponse('');
    setSources([]);
    setPromptVersion('');

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await workspace.getToken()}`,
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('ReadableStream not supported');
      }

      let accumulatedResponse = '';

      if (hasTextDecoderStream) {
        // Modern browsers with TextDecoderStream support
        const reader = response.body
          .pipeThrough(new TextDecoderStream())
          .getReader();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const lines = value.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as RagResponse;
                if (data.chunk) {
                  accumulatedResponse += data.chunk;
                  setResponse(accumulatedResponse);
                }
                if (data.done) {
                  if (data.sources) setSources(data.sources);
                  if (data.prompt_version) setPromptVersion(data.prompt_version);
                  options.onComplete?.(data.sources, data.prompt_version);
                }
              } catch (e) {
                console.warn('Failed to parse SSE data:', e);
              }
            }
          }
        }
      } else {
        // Fallback for browsers without TextDecoderStream
        const reader = response.body.getReader();
        let decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep the last incomplete line in the buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as RagResponse;
                if (data.chunk) {
                  accumulatedResponse += data.chunk;
                  setResponse(accumulatedResponse);
                }
                if (data.done) {
                  if (data.sources) setSources(data.sources);
                  if (data.prompt_version) setPromptVersion(data.prompt_version);
                  options.onComplete?.(data.sources, data.prompt_version);
                }
              } catch (e) {
                console.warn('Failed to parse SSE data:', e);
              }
            }
          }
        }

        // Process any remaining data
        if (buffer) {
          const finalChunk = decoder.decode();
          buffer += finalChunk;
          const lines = buffer.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as RagResponse;
                if (data.chunk) {
                  accumulatedResponse += data.chunk;
                  setResponse(accumulatedResponse);
                }
                if (data.done) {
                  if (data.sources) setSources(data.sources);
                  if (data.prompt_version) setPromptVersion(data.prompt_version);
                  options.onComplete?.(data.sources, data.prompt_version);
                }
              } catch (e) {
                console.warn('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      options.onError?.(error);
    } finally {
      setIsLoading(false);
    }
  }, [workspace, hasTextDecoderStream, options]);

  return {
    streamResponse,
    isLoading,
    error,
    response,
    sources,
    promptVersion,
  };
} 
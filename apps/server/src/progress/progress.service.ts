import { Injectable } from '@nestjs/common';
import { Subject, Observable } from 'rxjs';

export interface ProgressEvent {
  userId: string;
  taskId: string;
  step: number;
  label: string;
  status: 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  output?: string;
}

@Injectable()
export class ProgressService {
  private readonly progress$ = new Subject<ProgressEvent>();
  private readonly steeringCache = new Map<string, string>();
  private readonly approvalCache = new Map<string, boolean>();

  emitProgress(event: ProgressEvent): void {
    this.progress$.next(event);
  }

  getProgressStream(): Observable<ProgressEvent> {
    return this.progress$.asObservable();
  }

  setSteering(taskId: string, text: string): void {
    this.steeringCache.set(taskId, text);
  }

  getAndClearSteering(taskId: string): string | null {
    const text = this.steeringCache.get(taskId);
    if (text) {
      this.steeringCache.delete(taskId);
      return text;
    }
    return null;
  }

  setApproval(taskId: string, approved: boolean): void {
    this.approvalCache.set(taskId, approved);
  }

  getAndClearApproval(taskId: string): boolean | null {
    const approved = this.approvalCache.get(taskId);
    if (approved !== undefined) {
      this.approvalCache.delete(taskId);
      return approved;
    }
    return null;
  }
}

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReauthToastComponent } from './reauth-toast.component';
import { SessionState } from '../core/session.state';
import { HttpClientTestingModule } from '@angular/common/http/testing';

describe('ReauthToastComponent', () => {
  let fixture: ComponentFixture<ReauthToastComponent>;
  let component: ReauthToastComponent;
  let sessionState: SessionState;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ReauthToastComponent],
      imports: [HttpClientTestingModule],
      providers: [SessionState],
    }).compileComponents();

    fixture = TestBed.createComponent(ReauthToastComponent);
    component = fixture.componentInstance;
    sessionState = TestBed.inject(SessionState);
    fixture.detectChanges();
  });

  it('renders toast for inactivity reauthentication requirement', () => {
    sessionState.requireReauthentication('inactivity');
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain(
      'Your session expired due to inactivity. Please reauthenticate.',
    );
  });

  it('does not render toast when reauth is not required', () => {
    sessionState.clear();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).not.toContain('Your session expired due to inactivity');
  });
});

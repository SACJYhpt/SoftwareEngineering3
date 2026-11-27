import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CreateEvent from '../views/CreateEvent.vue'
import EditEvent from '../views/EditEvent.vue'
import { ApiError } from '../api'
import { auth } from '../auth'
import { formatRange } from '../format'

const { mockRequest, mockRoute, mockRouterPush } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockRoute: { params: { id: '42' }, fullPath: '/manage/events/42/edit' },
  mockRouterPush: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    request: (...args) => mockRequest(...args),
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockRouterPush }),
}))

const EVENT_TYPES = [{ id: 1, name: '參訪' }]
const DEPARTMENTS = [{ id: 10, name: '資訊工程學系' }]
const OFFICES = [{ id: 20, name: '學務處' }]

const OVERLAP_CONFLICT = {
  id: 7,
  name: '系上專題講座',
  start_time: '2030-05-10T02:00:00Z',
  end_time: '2030-05-10T04:00:00Z',
}

function makeOverlapError() {
  return new ApiError(
    409,
    'SCHEDULE_OVERLAP_CONFIRMATION_REQUIRED',
    '與同單位活動時間重疊，確認後可儲存',
    {},
    {
      code: 'SCHEDULE_OVERLAP_CONFIRMATION_REQUIRED',
      message: '與同單位活動時間重疊，確認後可儲存',
      conflicts: [OVERLAP_CONFLICT],
    },
  )
}

async function fillRequiredCreateFields(wrapper) {
  await wrapper.get('#name').setValue('資工系企業參訪')
  await wrapper.get('#type').setValue('參訪')
  await wrapper.get('#description').setValue('企業參訪說明')
  await wrapper.get('#start').setValue('2030-05-10T10:30')
  await wrapper.get('#end').setValue('2030-05-10T12:30')
  await wrapper.get('#location').setValue('資工系館')
  await wrapper.get('#reg-start').setValue('2030-05-01T09:00')
  await wrapper.get('#reg-end').setValue('2030-05-09T18:00')
  await wrapper.get('#contact').setValue('cs@ntou.edu.tw')
}

describe('C11 Schedule overlap warning - CreateEvent.vue & EditEvent.vue', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockRouterPush.mockReset()
    auth.token = 'test-token'
    auth.user = {
      id: 2,
      name: '馬老師',
      email: 'teacher@mail.ntou.edu.tw',
      role: 'manager',
      identity: 'teacher',
      department: { id: 10, name: '資訊工程學系' },
      grade: null,
      managed_units: [{ id: 10, name: '資訊工程學系' }],
    }
  })

  it('shows overlap dialog on CreateEvent, cancels without resending, and saves with confirm_overlap: true on confirm', async () => {
    mockRequest
      .mockResolvedValueOnce(EVENT_TYPES)
      .mockResolvedValueOnce(DEPARTMENTS)
      .mockResolvedValueOnce(OFFICES)
      .mockRejectedValueOnce(makeOverlapError())
      .mockRejectedValueOnce(makeOverlapError())
      .mockResolvedValueOnce({ id: 55 })

    const wrapper = mount(CreateEvent, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    await fillRequiredCreateFields(wrapper)

    // First submit triggers 409 overlap warning -> opens dialog without showing formError.
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('系上專題講座')
    expect(dialog.text()).toContain(formatRange(OVERLAP_CONFLICT.start_time, OVERLAP_CONFLICT.end_time))
    expect(wrapper.find('.alert-error').exists()).toBe(false)

    // Pressing Escape closes dialog without sending another request (L8).
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(mockRequest).toHaveBeenCalledTimes(4)

    // Submit again -> dialog reopens -> click 確認仍要儲存 -> sends confirm_overlap: true.
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('[role="dialog"]').findAll('button')[1].trigger('click')
    await flushPromises()

    const [path, options] = mockRequest.mock.calls[5]
    expect(path).toBe('/events')
    expect(options.method).toBe('POST')
    expect(options.body.confirm_overlap).toBe(true)
    expect(options.body.name).toBe('資工系企業參訪')
    expect(mockRouterPush).toHaveBeenCalledWith('/events/55')
  })

  it('API 直接成功時不顯示提醒對話框，直接導向活動詳情頁', async () => {
    mockRequest
      .mockResolvedValueOnce(EVENT_TYPES)
      .mockResolvedValueOnce(DEPARTMENTS)
      .mockResolvedValueOnce(OFFICES)
      .mockResolvedValueOnce({ id: 56 })

    const wrapper = mount(CreateEvent, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    await fillRequiredCreateFields(wrapper)

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(mockRequest).toHaveBeenCalledTimes(4)
    expect(mockRequest.mock.calls[3][1].body.confirm_overlap).toBeUndefined()
    expect(mockRouterPush).toHaveBeenCalledWith('/events/56')
  })

  it('shows overlap dialog on EditEvent and resends PATCH with confirm_overlap: true when confirmed', async () => {
    const existingEvent = {
      id: 42,
      unit_id: 10,
      unit: { id: 10, name: '資訊工程學系' },
      name: '既有活動',
      type: '參訪',
      description: '活動說明',
      location: '資工系館',
      contact_information: 'cs@ntou.edu.tw',
      start_time: '2030-05-12T02:00:00Z',
      end_time: '2030-05-12T04:00:00Z',
      registration_start: '2030-05-01T01:00:00Z',
      registration_deadline: '2030-05-09T10:00:00Z',
      capacity: 40,
      status: '開放中',
      notes: null,
      waitlist_enabled: false,
      waitlist_capacity: null,
      eligibility_identities: [],
      eligibility_department_ids: [],
      eligibility_grades: [],
    }

    mockRequest
      .mockResolvedValueOnce(existingEvent)
      .mockResolvedValueOnce(EVENT_TYPES)
      .mockResolvedValueOnce(DEPARTMENTS)
      .mockResolvedValueOnce(OFFICES)
      .mockRejectedValueOnce(makeOverlapError())
      .mockResolvedValueOnce({ ...existingEvent, start_time: '2030-05-10T02:30:00Z', end_time: '2030-05-10T04:30:00Z' })

    const wrapper = mount(EditEvent, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    await wrapper.get('#start').setValue('2030-05-10T10:30')
    await wrapper.get('#end').setValue('2030-05-10T12:30')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('系上專題講座')
    expect(wrapper.find('.alert-error').exists()).toBe(false)

    await dialog.findAll('button')[1].trigger('click')
    await flushPromises()

    const [path, options] = mockRequest.mock.calls[5]
    expect(path).toBe('/events/42')
    expect(options.method).toBe('PATCH')
    expect(options.body).toEqual({
      start_time: '2030-05-10T10:30:00+08:00',
      end_time: '2030-05-10T12:30:00+08:00',
      confirm_overlap: true,
    })
    expect(mockRouterPush).toHaveBeenCalledWith('/events/42')
  })
})

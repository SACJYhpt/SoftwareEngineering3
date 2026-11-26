import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EventDetail from '../views/EventDetail.vue'
import { ApiError } from '../api'
import { auth } from '../auth'
import { formatRange } from '../format'

const { mockRequest, mockRoute, mockRouterPush, mockRouterReplace } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockRoute: { params: { id: '42' }, fullPath: '/events/42' },
  mockRouterPush: vi.fn(),
  mockRouterReplace: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    request: (...args) => mockRequest(...args),
    download: vi.fn(),
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockRouterPush, replace: mockRouterReplace }),
}))

function makeEvent(overrides = {}) {
  return {
    id: 42,
    unit_id: 10,
    unit: { id: 10, name: '資訊工程學系' },
    name: '企業參訪',
    type: '參訪',
    description: '下午 15:00–17:00 活動',
    location: '資工系館',
    contact_information: 'cs@ntou.edu.tw',
    start_time: '2030-05-10T07:00:00Z', // 15:00+08:00
    end_time: '2030-05-10T09:00:00Z',   // 17:00+08:00
    registration_start: '2030-05-01T01:00:00Z',
    registration_deadline: '2030-05-09T10:00:00Z',
    capacity: 40,
    registration_count: 5,
    status: '開放中',
    my_registration_status: '未報名',
    can_register: true,
    notes: null,
    waitlist_enabled: false,
    waitlist_capacity: null,
    eligibility_identities: [],
    eligibility_department_ids: [],
    eligibility_grades: [],
    eligibility_description: '不限',
    ...overrides,
  }
}

function mountDetail() {
  return mount(EventDetail, {
    global: {
      stubs: {
        RouterLink: {
          props: ['to'],
          template: '<a :href="typeof to === \'string\' ? to : to.path"><slot /></a>',
        },
      },
    },
  })
}

describe('D04 Time conflict check - EventDetail.vue', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockRouterPush.mockReset()
    mockRouterReplace.mockReset()
    mockRoute.params.id = '42'
    mockRoute.fullPath = '/events/42'
    auth.token = 'test-token'
    auth.user = {
      id: 1,
      name: '王小明',
      email: 'student@mail.ntou.edu.tw',
      role: 'member',
      identity: 'student',
      department: { id: 10, name: '資訊工程學系' },
      grade: 3,
      managed_units: [],
    }
  })

  it('rejects overlapping event (15:00-17:00 vs 14:00-16:00), displays conflict name/time, and supports D11 switch', async () => {
    const conflict = {
      event_id: 12,
      name: '程式競賽說明會',
      start_time: '2030-05-10T06:00:00Z', // 14:00+08:00
      end_time: '2030-05-10T08:00:00Z',   // 16:00+08:00
      status: 'registered',
      waitlist_position: null,
      registration_closed: false,
      action: 'switch',
      action_path: '/events/12/registrations/me',
    }
    const conflictError = new ApiError(
      409,
      'TIME_CONFLICT',
      '與既有報名或候補活動撞期，請選擇取消本次或確認改報名',
      {},
      { code: 'TIME_CONFLICT', message: '與既有報名或候補活動撞期，請選擇取消本次或確認改報名', conflicts: [conflict] },
    )

    mockRequest
      .mockResolvedValueOnce(makeEvent())
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce(makeEvent())
      .mockResolvedValueOnce({ message: '報名成功', status: 'registered' })
      .mockResolvedValueOnce(makeEvent({ my_registration_status: '已報名', can_register: false, registration_count: 6 }))

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    const conflictBox = wrapper.get('.conflict-error')
    expect(conflictBox.text()).toContain('程式競賽說明會')
    expect(conflictBox.text()).toContain(formatRange(conflict.start_time, conflict.end_time))
    expect(conflictBox.text()).toContain('已報名')
    expect(conflictBox.get('a[href="/events/12"]').text()).toBe('程式競賽說明會')
    expect(conflictBox.find('.conflict-cancel-link').exists()).toBe(false)

    const switchBtn = conflictBox.get('.conflict-switch-btn')
    expect(switchBtn.text()).toBe('取消原活動並改報名')

    await switchBtn.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(mockRequest).toHaveBeenCalledWith('/events/42/registrations/switch', {
      method: 'POST',
      body: { source_event_ids: [12], source_status: 'registered', confirmed: true },
    })
    expect(wrapper.find('.conflict-error').exists()).toBe(false)
    expect(wrapper.text()).toContain('報名成功')
    confirmSpy.mockRestore()
  })

  it('registers successfully for back-to-back event (16:00-18:00 after 14:00-16:00)', async () => {
    const adjacentEvent = makeEvent({
      start_time: '2030-05-10T08:00:00Z', // 16:00+08:00
      end_time: '2030-05-10T10:00:00Z',   // 18:00+08:00
    })
    mockRequest
      .mockResolvedValueOnce(adjacentEvent)
      .mockResolvedValueOnce({ already_registered: false, status: 'registered' })
      .mockResolvedValueOnce({ ...adjacentEvent, my_registration_status: '已報名', can_register: false, registration_count: 6 })

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('報名成功！')
    expect(wrapper.find('.conflict-error').exists()).toBe(false)
  })

  it('shows cancellation-request link (E11) and hides switch button when conflicting event is closed', async () => {
    const closedConflict = {
      event_id: 99,
      name: '已截止之講座',
      start_time: '2030-05-10T06:00:00Z',
      end_time: '2030-05-10T08:00:00Z',
      status: 'registered',
      waitlist_position: null,
      registration_closed: true,
      action: 'request_cancellation',
      action_path: '/events/99/cancellation-requests',
    }
    const conflictError = new ApiError(
      409,
      'TIME_CONFLICT',
      '與既有報名或候補活動撞期，請選擇取消本次或確認改報名',
      {},
      { code: 'TIME_CONFLICT', message: '與既有報名或候補活動撞期，請選擇取消本次或確認改報名', conflicts: [closedConflict] },
    )

    mockRequest
      .mockResolvedValueOnce(makeEvent())
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce(makeEvent())

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    const conflictBox = wrapper.get('.conflict-error')
    expect(conflictBox.text()).toContain('已截止之講座')
    expect(conflictBox.text()).toContain('已報名（已截止）')
    expect(conflictBox.find('.conflict-switch-btn').exists()).toBe(false)

    const cancelLink = conflictBox.get('a[href="/events/99/cancellation-request"]')
    expect(cancelLink.text()).toBe('申請取消')
  })

  it('shows backend error when switch fails due to EVENT_FULL', async () => {
    const conflict = {
      event_id: 12,
      name: '程式競賽說明會',
      start_time: '2030-05-10T06:00:00Z',
      end_time: '2030-05-10T08:00:00Z',
      status: 'registered',
      waitlist_position: null,
      registration_closed: false,
      action: 'switch',
      action_path: '/events/12/registrations/me',
    }
    const conflictError = new ApiError(409, 'TIME_CONFLICT', '與既有報名撞期', {}, { conflicts: [conflict] })
    const fullError = new ApiError(409, 'EVENT_FULL', '名額已滿', {}, { code: 'EVENT_FULL', message: '名額已滿' })

    mockRequest
      .mockResolvedValueOnce(makeEvent())
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce(makeEvent())
      .mockRejectedValueOnce(fullError)
      .mockResolvedValueOnce(makeEvent({ status: '已額滿', can_register: false }))

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    await wrapper.get('.conflict-switch-btn').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('改報名失敗：名額已滿')
    confirmSpy.mockRestore()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EventDetail from '../views/EventDetail.vue'
import { ApiError } from '../api'
import { auth } from '../auth'

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
    name: '資工系企業參訪',
    type: '參訪',
    description: '限資工系學生參加',
    location: '資工系館',
    contact_information: 'cs@ntou.edu.tw',
    start_time: '2030-05-10T02:00:00Z',
    end_time: '2030-05-10T04:00:00Z',
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
    eligibility_identities: ['student'],
    eligibility_department_ids: [10],
    eligibility_grades: [],
    eligibility_description: '身分別：學生；系所／單位：資訊工程學系',
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

describe('D03 Eligibility check - EventDetail.vue', () => {
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

  it('registers successfully when user meets eligibility restrictions', async () => {
    mockRequest
      .mockResolvedValueOnce(makeEvent())
      .mockResolvedValueOnce({ already_registered: false, status: 'registered' })
      .mockResolvedValueOnce(makeEvent({ my_registration_status: '已報名', can_register: false, registration_count: 6 }))

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledWith('/events/42/registrations', { method: 'POST' })
    expect(wrapper.text()).toContain('報名成功！')
    expect(wrapper.find('.eligibility-error').exists()).toBe(false)
  })

  it('shows structured eligibility error with failed conditions and profile link when rejected, and retains it after reload', async () => {
    const mismatchError = new ApiError(
      409,
      'ELIGIBILITY_MISMATCH',
      '系所／單位不符；身分別：學生；系所／單位：資訊工程學系',
      {},
      {
        code: 'ELIGIBILITY_MISMATCH',
        message: '系所／單位不符；身分別：學生；系所／單位：資訊工程學系',
        conditions: ['系所／單位不符'],
      },
    )

    mockRequest
      .mockResolvedValueOnce(makeEvent())
      .mockRejectedValueOnce(mismatchError)
      .mockResolvedValueOnce(makeEvent())

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    // load() was called after failure, yet the structured error must remain visible.
    expect(mockRequest).toHaveBeenCalledTimes(3)
    const errorBox = wrapper.get('.eligibility-error')
    expect(errorBox.text()).toContain('不符合報名資格')
    expect(errorBox.text()).toContain('系所／單位不符')
    expect(errorBox.text()).toContain('身分別：學生；系所／單位：資訊工程學系')

    const profileLink = errorBox.get('a[href="/me/profile"]')
    expect(profileLink.text()).toBe('前往更新個人資料')
  })

  it('allows any ordinary user to register when no eligibility restrictions are set', async () => {
    const unrestricted = makeEvent({
      eligibility_identities: [],
      eligibility_department_ids: [],
      eligibility_grades: [],
      eligibility_description: '不限',
    })
    mockRequest
      .mockResolvedValueOnce(unrestricted)
      .mockResolvedValueOnce({ already_registered: false, status: 'registered' })
      .mockResolvedValueOnce({ ...unrestricted, my_registration_status: '已報名', can_register: false, registration_count: 6 })

    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('.action button.btn-large').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('報名成功！')
    expect(wrapper.find('.eligibility-error').exists()).toBe(false)
  })
})

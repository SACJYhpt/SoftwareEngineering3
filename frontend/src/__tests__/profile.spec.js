import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Profile from '../views/Profile.vue'
import { auth } from '../auth'

const { mockRequest, mockRefreshUser } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockRefreshUser: vi.fn(),
}))

vi.mock('../api', () => ({
  request: (...args) => mockRequest(...args),
}))

vi.mock('../auth', async () => {
  const { reactive } = await import('vue')
  return {
    auth: reactive({ token: 'test-token', user: null }),
    refreshUser: (...args) => mockRefreshUser(...args),
  }
})

const DEPARTMENTS = [
  { id: 10, name: '資訊工程學系' },
  { id: 11, name: '電機工程學系' },
]

const OFFICES = [
  { id: 20, name: '學務處' },
  { id: 21, name: '教務處' },
]

describe('A10 Department and grade - Profile.vue', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockRefreshUser.mockReset()
    mockRefreshUser.mockImplementation(async () => auth.user)
  })

  it('displays identity as read-only with contact-admin hint and loads departments for student', async () => {
    auth.user = {
      id: 1,
      name: '王小明',
      email: 'student@mail.ntou.edu.tw',
      role: 'member',
      identity: 'student',
      department: { id: 11, name: '電機工程學系' },
      grade: 2,
      managed_units: [],
    }
    mockRequest.mockResolvedValueOnce(DEPARTMENTS)

    const wrapper = mount(Profile)
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledWith('/units?kind=department')
    const identityInput = wrapper.get('#profile-identity')
    expect(identityInput.element.value).toBe('學生')
    expect(identityInput.element.disabled).toBe(true)
    expect(identityInput.element.readOnly).toBe(true)
    expect(wrapper.text()).toContain('如需更正請聯絡系統管理員')
    expect(wrapper.find('#profile-grade').exists()).toBe(true)
  })

  it('submits only department_id and grade (without identity) for student and refreshes user', async () => {
    auth.user = {
      id: 1,
      name: '王小明',
      email: 'student@mail.ntou.edu.tw',
      role: 'member',
      identity: 'student',
      department: { id: 11, name: '電機工程學系' },
      grade: 2,
      managed_units: [],
    }
    mockRequest
      .mockResolvedValueOnce(DEPARTMENTS)
      .mockResolvedValueOnce({
        ...auth.user,
        department: { id: 10, name: '資訊工程學系' },
        grade: 3,
      })
    mockRefreshUser.mockImplementationOnce(async () => {
      auth.user = {
        ...auth.user,
        department: { id: 10, name: '資訊工程學系' },
        grade: 3,
      }
      return auth.user
    })

    const wrapper = mount(Profile)
    await flushPromises()

    await wrapper.get('#profile-department').setValue(10)
    await wrapper.get('#profile-grade').setValue(3)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledTimes(2)
    const [path, options] = mockRequest.mock.calls[1]
    expect(path).toBe('/me/profile')
    expect(options.method).toBe('PATCH')
    expect(Object.keys(options.body).sort()).toEqual(['department_id', 'grade'])
    expect(options.body).toEqual({ department_id: 10, grade: 3 })
    expect(options.body).not.toHaveProperty('identity')
    expect(mockRefreshUser).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已成立的報名不受影響，新的報名將以更新後的資料判斷資格')
  })

  it('hides grade and sends grade: null for teacher', async () => {
    auth.user = {
      id: 2,
      name: '馬老師',
      email: 'teacher@mail.ntou.edu.tw',
      role: 'manager',
      identity: 'teacher',
      department: { id: 10, name: '資訊工程學系' },
      grade: null,
      managed_units: [],
    }
    mockRequest
      .mockResolvedValueOnce(DEPARTMENTS)
      .mockResolvedValueOnce({ ...auth.user, department: { id: 11, name: '電機工程學系' } })

    const wrapper = mount(Profile)
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledWith('/units?kind=department')
    expect(wrapper.find('#profile-grade').exists()).toBe(false)

    await wrapper.get('#profile-department').setValue(11)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const [path, options] = mockRequest.mock.calls[1]
    expect(path).toBe('/me/profile')
    expect(options.body).toEqual({ department_id: 11, grade: null })
    expect(options.body).not.toHaveProperty('identity')
    expect(mockRefreshUser).toHaveBeenCalledTimes(1)
  })

  it('loads offices, hides grade, and sends grade: null for staff', async () => {
    auth.user = {
      id: 3,
      name: '林承辦',
      email: 'staff@mail.ntou.edu.tw',
      role: 'member',
      identity: 'staff',
      department: { id: 20, name: '學務處' },
      grade: null,
      managed_units: [],
    }
    mockRequest
      .mockResolvedValueOnce(OFFICES)
      .mockResolvedValueOnce({ ...auth.user, department: { id: 21, name: '教務處' } })

    const wrapper = mount(Profile)
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledWith('/units?kind=office')
    expect(wrapper.find('#profile-grade').exists()).toBe(false)
    expect(wrapper.get('#profile-identity').element.value).toBe('行政人員')

    await wrapper.get('#profile-department').setValue(21)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const [path, options] = mockRequest.mock.calls[1]
    expect(path).toBe('/me/profile')
    expect(options.body).toEqual({ department_id: 21, grade: null })
    expect(options.body).not.toHaveProperty('identity')
    expect(mockRefreshUser).toHaveBeenCalledTimes(1)
  })

  it('blocks submit when student grade is missing', async () => {
    auth.user = {
      id: 4,
      name: '新生',
      email: 'fresh@mail.ntou.edu.tw',
      role: 'member',
      identity: 'student',
      department: { id: 10, name: '資訊工程學系' },
      grade: null,
      managed_units: [],
    }
    mockRequest.mockResolvedValueOnce(DEPARTMENTS)

    const wrapper = mount(Profile)
    await flushPromises()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockRequest).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('學生須選擇年級')
  })
})

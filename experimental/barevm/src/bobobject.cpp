//*****************************************************************************
// bob: base BobObject
//
// Eli Bendersky (eliben@gmail.com)
// This code is in the public domain
//*****************************************************************************
#include "bobobject.h"
#include "utils.h"
#include <typeinfo>
#include <cstdlib>

using namespace std;


BobObject::BobObject()
    : m_gc_marked(false)
{
}


BobObject::~BobObject()
{
}


bool objects_equal(const BobObject* lhs, const BobObject* rhs)
{
    if (lhs == rhs)
        return true;
    else if (typeid(*lhs) != typeid(*rhs))
        return false;
    else
        return lhs->equals_to(*rhs);
}


void* BobObject::operator new(size_t sz)
{
    return BobAllocator::get().allocate_object(sz);
}


void BobObject::operator delete(void* p)
{
    BobAllocator::get().release_object(p);
}


BobAllocator BobAllocator::the_allocator;


void* BobAllocator::allocate_object(size_t sz)
{
    void* mem = ::operator new(sz);
    live_objects.push_back(static_cast<BobObject*>(mem));
    total_alloc_size += sz;
    return mem;
}


void BobAllocator::release_object(void* p)
{
    ::operator delete(p);
}


string BobAllocator::stats_general() const
{
    string s = format_string("Number of live objects: %u\n", live_objects.size());
    s += format_string("Total allocation size: %u\n", total_alloc_size);
    return s;
}


string BobAllocator::stats_all_live() const
{
    string s;
    for (list<BobObject*>::const_iterator it = live_objects.begin(); 
            it != live_objects.end(); ++it) {
        s += (*it)->repr() + "\n";
    }
    return s;
}


void BobAllocator::run_gc()
{
    // Mark each object found in the roots. Marking as implemented by
    // BobObjectis subclasses is recursive.
    // Go over all the live objects:
    //   * Marked objects are used and thus have to keep living. Clear their
    //     mark flag.
    //   * Unmarked objects aren't used and can be deleted.
}

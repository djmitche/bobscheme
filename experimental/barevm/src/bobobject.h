//*****************************************************************************
// bob: base BobObject
//
// Eli Bendersky (eliben@gmail.com)
// This code is in the public domain
//*****************************************************************************
#ifndef BOBOBJECT_H
#define BOBOBJECT_H

#include <string>


// Abstract base class for all objects managed by the Bob VM
//
class BobObject 
{
public:
    BobObject()
    {}

    virtual ~BobObject()
    {}

    virtual std::string repr() const = 0;
    friend bool objects_equal(const BobObject*, const BobObject*);
protected:
    // Derived objects must override this comparison function. An object can
    // assume that 'other' is of the same type as it is.
    //
    virtual bool equals_to(const BobObject& other) const = 0;
};


// Compare two objects of any type derived from BobObject
//
bool objects_equal(const BobObject*, const BobObject*);


#endif /* BOBOBJECT_H */
